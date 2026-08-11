import { HumanQueuePage } from "./HumanQueuePage";
import { ReviewsPage } from "./ReviewsPage";

/** Cockpit L3: human queue + reviews in one surface. */
export function HumanGatePage() {
  return (
    <div className="space-y-6">
      <HumanQueuePage />
      <ReviewsPage />
    </div>
  );
}
