import type { VisualQueryPlan } from "../../types/api";

/** Global OCR/ASR lists belong to Search, not to event-indexed Temporal slots. */
export function temporalEventsFromPlan(plan: VisualQueryPlan) {
  return plan.events.map((event) => ({
    text: event.vi || event.en,
    translation: event.en,
    ocr: event.ocr,
    asr: event.asr,
    anchor: event.anchor,
  }));
}
