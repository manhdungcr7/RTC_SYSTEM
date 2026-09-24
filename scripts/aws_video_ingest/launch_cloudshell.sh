#!/usr/bin/env bash
# Run this file in AWS CloudShell, not on the Windows computer.
# Usage: bash launch_cloudshell.sh sources.tsv [bucket-name]
set -Eeuo pipefail
export AWS_PAGER=""

REGION="ap-southeast-1"
EXPECTED_ACCOUNT="735792832986"
DEFAULT_BUCKET="video-data-735792832986-ap-southeast-1-an"
ROLE="AICVideoIngestSingaporeRole"
PROFILE="AICVideoIngestSingaporeProfile"
POLICY="AICVideoIngestSingaporeBucketOnly"
GROUP_NAME="aic-video-ingest-singapore"
WORK_ROOT="$HOME/aic-video-ingest-run"
VOLUME_GB="${VOLUME_GB:-100}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.small}"

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: bash launch_cloudshell.sh sources.tsv [bucket-name]" >&2
  exit 2
fi
MANIFEST="$(readlink -f -- "$1")"
BUCKET="${2:-$DEFAULT_BUCKET}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "$MANIFEST" || ! -f "$SCRIPT_DIR/ingest_videos.py" ]]; then
  echo "Missing manifest or ingest_videos.py" >&2
  exit 2
fi
if [[ ! "$VOLUME_GB" =~ ^[0-9]+$ ]] || (( VOLUME_GB < 20 )); then
  echo "VOLUME_GB must be an integer >= 20" >&2
  exit 2
fi

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
if [[ "$ACCOUNT" != "$EXPECTED_ACCOUNT" ]]; then
  echo "Wrong AWS account: $ACCOUNT (expected $EXPECTED_ACCOUNT)" >&2
  exit 1
fi
BUCKET_REGION="$(aws s3api get-bucket-location --bucket "$BUCKET" --region "$REGION" --query LocationConstraint --output text)"
if [[ "$BUCKET_REGION" != "$REGION" ]]; then
  echo "Bucket $BUCKET is in $BUCKET_REGION, expected $REGION" >&2
  exit 1
fi

# The first 14 ZIPs have already been uploaded. Never start an accidental
# replay of this bundled manifest; make a targeted recovery manifest instead.
if [[ "$(basename -- "$MANIFEST")" == "sources.tsv" ]]; then
  echo "The first 14 ZIPs are complete. Use a new manifest with only new or missing ZIPs." >&2
  exit 1
fi

mkdir -p -- "$WORK_ROOT"
cat > "$WORK_ROOT/ec2-trust.json" <<'JSON'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}
JSON
cat > "$WORK_ROOT/s3-policy.json" <<JSON
{"Version":"2012-10-17","Statement":[
  {"Effect":"Allow","Action":["s3:ListBucket"],"Resource":"arn:aws:s3:::$BUCKET"},
  {"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:AbortMultipartUpload","s3:ListMultipartUploadParts"],"Resource":"arn:aws:s3:::$BUCKET/*"}
]}
JSON

if ! aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE" \
    --assume-role-policy-document "file://$WORK_ROOT/ec2-trust.json" \
    --description "Temporary EC2 upload to the AIC Singapore video bucket" >/dev/null
fi
aws iam put-role-policy --role-name "$ROLE" --policy-name "$POLICY" \
  --policy-document "file://$WORK_ROOT/s3-policy.json"
if ! aws iam get-instance-profile --instance-profile-name "$PROFILE" >/dev/null 2>&1; then
  aws iam create-instance-profile --instance-profile-name "$PROFILE" >/dev/null
fi
PROFILE_ROLE="$(aws iam get-instance-profile --instance-profile-name "$PROFILE" \
  --query 'InstanceProfile.Roles[0].RoleName' --output text)"
if [[ "$PROFILE_ROLE" == "None" ]]; then
  aws iam add-role-to-instance-profile --instance-profile-name "$PROFILE" \
    --role-name "$ROLE"
elif [[ "$PROFILE_ROLE" != "$ROLE" ]]; then
  echo "Instance profile $PROFILE already contains another role: $PROFILE_ROLE" >&2
  exit 1
fi

VPC="${VPC_ID:-$(aws ec2 describe-vpcs --region "$REGION" \
  --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)}"
if [[ -z "$VPC" || "$VPC" == "None" ]]; then
  echo "No default VPC. Set VPC_ID and SUBNET_ID before running." >&2
  exit 1
fi
SUBNET="${SUBNET_ID:-$(aws ec2 describe-subnets --region "$REGION" \
  --filters Name=vpc-id,Values="$VPC" Name=default-for-az,Values=true \
  --query 'Subnets[0].SubnetId' --output text)}"
if [[ -z "$SUBNET" || "$SUBNET" == "None" ]]; then
  echo "No default subnet. Set SUBNET_ID before running." >&2
  exit 1
fi
GROUP="$(aws ec2 describe-security-groups --region "$REGION" \
  --filters Name=vpc-id,Values="$VPC" Name=group-name,Values="$GROUP_NAME" \
  --query 'SecurityGroups[0].GroupId' --output text)"
if [[ "$GROUP" == "None" ]]; then
  GROUP="$(aws ec2 create-security-group --region "$REGION" \
    --group-name "$GROUP_NAME" --vpc-id "$VPC" \
    --description 'AIC ingest: outbound only, no inbound connections' \
    --query GroupId --output text)"
fi
INBOUND_COUNT="$(aws ec2 describe-security-groups --region "$REGION" \
  --group-ids "$GROUP" --query 'length(SecurityGroups[0].IpPermissions)' --output text)"
if [[ "$INBOUND_COUNT" != "0" ]]; then
  echo "Security group $GROUP has inbound rules; refusing to launch." >&2
  exit 1
fi

AMI="$(aws ssm get-parameter --region "$REGION" \
  --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query Parameter.Value --output text)"
ROOT_DEVICE="$(aws ec2 describe-images --region "$REGION" --image-ids "$AMI" \
  --query 'Images[0].RootDeviceName' --output text)"

SCRIPT_B64="$(gzip -c "$SCRIPT_DIR/ingest_videos.py" | base64 -w0)"
MANIFEST_B64="$(gzip -c "$MANIFEST" | base64 -w0)"
USER_DATA="$WORK_ROOT/user-data.sh"
{
  cat <<'USERDATA'
#!/bin/bash
set -Eeuo pipefail
exec > >(tee -a /var/log/aic-video-ingest.log /dev/console) 2>&1
cleanup() {
  local status=$?
  trap - EXIT
  rm -rf -- /var/lib/aic-video-ingest
  if [[ "$status" -eq 0 ]]; then
    echo AIC_INGEST_DONE
  else
    echo "AIC_INGEST_FAILED exit=$status"
  fi
  shutdown -h now
}
trap cleanup EXIT
echo AIC_INGEST_BOOT
mkdir -p /opt/aic-video-ingest /var/lib/aic-video-ingest
command -v python3
command -v aws
command -v curl
USERDATA
  printf "printf '%%s' '%s' | base64 -d | gzip -d > /opt/aic-video-ingest/ingest_videos.py\n" "$SCRIPT_B64"
  printf "printf '%%s' '%s' | base64 -d | gzip -d > /opt/aic-video-ingest/sources.tsv\n" "$MANIFEST_B64"
  printf 'python3 /opt/aic-video-ingest/ingest_videos.py --manifest /opt/aic-video-ingest/sources.tsv --bucket %q --region %q --work-dir /var/lib/aic-video-ingest\n' "$BUCKET" "$REGION"
} > "$USER_DATA"
USER_DATA_BYTES="$(wc -c < "$USER_DATA")"
if (( USER_DATA_BYTES > 16384 )); then
  echo "EC2 user data is too large ($USER_DATA_BYTES bytes; max 16384). Use a shorter manifest." >&2
  exit 1
fi

# IAM profile attachment may take a few seconds to propagate.
sleep 12
INSTANCE_ID="$(aws ec2 run-instances --region "$REGION" \
  --image-id "$AMI" --instance-type "$INSTANCE_TYPE" --count 1 \
  --iam-instance-profile "Name=$PROFILE" \
  --network-interfaces "DeviceIndex=0,SubnetId=$SUBNET,Groups=$GROUP,AssociatePublicIpAddress=true" \
  --block-device-mappings "DeviceName=$ROOT_DEVICE,Ebs={VolumeSize=$VOLUME_GB,VolumeType=gp3,DeleteOnTermination=true,Encrypted=true}" \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled \
  --instance-initiated-shutdown-behavior terminate \
  --user-data "file://$USER_DATA" \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=AIC-Video-Ingest-Singapore},{Key=Purpose,Value=AICVideoIngest}]' \
  --query 'Instances[0].InstanceId' --output text)"
printf '%s\n' "$INSTANCE_ID" > "$WORK_ROOT/instance-id.txt"
echo "STARTED $INSTANCE_ID in $REGION; bucket=$BUCKET; manifest=$MANIFEST"
echo "Log: aws ec2 get-console-output --region $REGION --instance-id $INSTANCE_ID --latest --query Output --output text | tail -n 30"
