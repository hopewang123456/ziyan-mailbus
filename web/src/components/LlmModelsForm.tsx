import { ConfigPage } from "../pages/ConfigPage";

/**
 * Legacy/named export for model settings.
 * Cockpit Agent knob uses ConfigPage variant="llm" directly; this wraps the same API surface.
 */
export function LlmModelsForm() {
  return <ConfigPage variant="llm" />;
}
