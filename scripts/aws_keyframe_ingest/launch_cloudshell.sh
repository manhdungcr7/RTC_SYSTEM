#!/usr/bin/env bash
# Run from AWS CloudShell in account 735792832986. Requires the existing
# AICVideoIngestSingaporeProfile; creates no IAM role, policy, or access key.
set -Eeuo pipefail
export AWS_PAGER=""

REGION=ap-southeast-1
ACCOUNT=735792832986
BUCKET=video-data-735792832986-ap-southeast-1-an
PROFILE=AICVideoIngestSingaporeProfile
GROUP_NAME=aic-video-ingest-singapore
VOLUME_GB="${VOLUME_GB:-100}"
INSTANCE_TYPE="${INSTANCE_TYPE:-m7i-flex.large}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_FILE="${MANIFEST_FILE:-$SCRIPT_DIR/datasets.txt}"
WORK_ROOT="$HOME/aic-keyframe-ingest-run"

[[ -f "$SCRIPT_DIR/ingest_keyframes.py" && -f "$MANIFEST_FILE" ]] || {
  echo 'Missing ingest_keyframes.py or manifest file' >&2; exit 2;
}
[[ "$(aws sts get-caller-identity --query Account --output text)" == "$ACCOUNT" ]] || {
  echo 'Wrong AWS account' >&2; exit 1;
}
[[ "$(aws s3api get-bucket-location --bucket "$BUCKET" --region "$REGION" --query LocationConstraint --output text)" == "$REGION" ]] || {
  echo 'Bucket is not in Singapore' >&2; exit 1;
}
[[ "$(aws iam get-instance-profile --instance-profile-name "$PROFILE" --query 'InstanceProfile.Roles[0].RoleName' --output text)" == AICVideoIngestSingaporeRole ]] || {
  echo 'Expected existing IAM role is unavailable' >&2; exit 1;
}

ACTIVE="$(aws ec2 describe-instances --region "$REGION" \
  --filters Name=tag:Purpose,Values=AICKeyframeIngest Name=instance-state-name,Values=pending,running,stopping,stopped \
  --query 'Reservations[].Instances[].InstanceId' --output text)"
[[ -z "$ACTIVE" ]] || { echo "An ingest instance already exists: $ACTIVE" >&2; exit 1; }

VPC="$(aws ec2 describe-vpcs --region "$REGION" --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)"
SUBNET="$(aws ec2 describe-subnets --region "$REGION" \
  --filters Name=vpc-id,Values="$VPC" Name=default-for-az,Values=true \
  --query 'Subnets[0].SubnetId' --output text)"
GROUP="$(aws ec2 describe-security-groups --region "$REGION" \
  --filters Name=vpc-id,Values="$VPC" Name=group-name,Values="$GROUP_NAME" \
  --query 'SecurityGroups[0].GroupId' --output text)"
[[ "$VPC" != None && "$SUBNET" != None && "$GROUP" != None ]] || {
  echo 'Expected default network/security group is unavailable' >&2; exit 1;
}
[[ "$(aws ec2 describe-security-groups --region "$REGION" --group-ids "$GROUP" \
  --query 'length(SecurityGroups[0].IpPermissions)' --output text)" == 0 ]] || {
  echo 'Ingest security group unexpectedly has inbound rules' >&2; exit 1;
}
AMI="$(aws ssm get-parameter --region "$REGION" \
  --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query Parameter.Value --output text)"
ROOT_DEVICE="$(aws ec2 describe-images --region "$REGION" --image-ids "$AMI" \
  --query 'Images[0].RootDeviceName' --output text)"

mkdir -p -- "$WORK_ROOT"
SCRIPT_B64="$(gzip -c "$SCRIPT_DIR/ingest_keyframes.py" | base64 -w0)"
MANIFEST_B64="$(gzip -c "$MANIFEST_FILE" | base64 -w0)"
DATASET_COUNT="$(grep -cvE '^([[:space:]]*|#)' "$MANIFEST_FILE")"
USER_DATA="$WORK_ROOT/user-data.sh"
{
  cat <<'USERDATA'
#!/bin/bash
set -Eeuo pipefail
exec > >(tee -a /var/log/aic-keyframe-ingest.log /dev/console) 2>&1
cleanup() {
  local status=$?
  trap - EXIT
  rm -rf -- /var/lib/aic-keyframe-ingest
  if [[ "$status" -eq 0 ]]; then
    echo AIC_KEYFRAME_INGEST_DONE
  else
    echo "AIC_KEYFRAME_INGEST_FAILED exit=$status"
    sleep 120  # leave console output available briefly for diagnosis
  fi
  shutdown -h now
}
trap cleanup EXIT
echo AIC_KEYFRAME_INGEST_BOOT
dnf -y install python3.11 python3.11-pip
python3.11 -m pip install --no-cache-dir --target /opt/aic-keyframe-packages kagglehub boto3
mkdir -p /opt/aic-keyframe-ingest /var/lib/aic-keyframe-ingest
USERDATA
  printf "printf '%%s' '%s' | base64 -d | gzip -d > /opt/aic-keyframe-ingest/ingest_keyframes.py\n" "$SCRIPT_B64"
  printf "printf '%%s' '%s' | base64 -d | gzip -d > /opt/aic-keyframe-ingest/datasets.txt\n" "$MANIFEST_B64"
  printf 'PYTHONPATH=/opt/aic-keyframe-packages python3.11 /opt/aic-keyframe-ingest/ingest_keyframes.py --manifest /opt/aic-keyframe-ingest/datasets.txt --bucket %q --region %q --work-dir /var/lib/aic-keyframe-ingest --workers 24\n' "$BUCKET" "$REGION"
} > "$USER_DATA"
BYTES="$(wc -c < "$USER_DATA")"
(( BYTES <= 16384 )) || { echo "User data too large: $BYTES bytes" >&2; exit 1; }

INSTANCE_ID="$(aws ec2 run-instances --region "$REGION" \
  --image-id "$AMI" --instance-type "$INSTANCE_TYPE" --count 1 \
  --iam-instance-profile "Name=$PROFILE" \
  --network-interfaces "DeviceIndex=0,SubnetId=$SUBNET,Groups=$GROUP,AssociatePublicIpAddress=true" \
  --block-device-mappings "DeviceName=$ROOT_DEVICE,Ebs={VolumeSize=$VOLUME_GB,VolumeType=gp3,DeleteOnTermination=true,Encrypted=true}" \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled \
  --instance-initiated-shutdown-behavior terminate \
  --user-data "file://$USER_DATA" \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=AIC-Keyframe-Ingest-Singapore},{Key=Purpose,Value=AICKeyframeIngest}]' \
  --query 'Instances[0].InstanceId' --output text)"
printf '%s\n' "$INSTANCE_ID" > "$WORK_ROOT/instance-id.txt"
echo "STARTED $INSTANCE_ID bucket=$BUCKET region=$REGION datasets=$DATASET_COUNT volume=${VOLUME_GB}GB"
echo "One-time log: aws ec2 get-console-output --region $REGION --instance-id $INSTANCE_ID --latest --query Output --output text | tail -n 40"
