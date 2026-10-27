import { ConsolePageHeader } from "../../components/console/ConsoleKit";
import { IntegrationsPage } from "../IntegrationsPage";

/** 集成管理（P3）— 复用驾驶舱同款 IntegrationsPage（组件双处消费的既定模式，弹窗内为只读快捷视图，此处为完整管理）。 */
export function ConsoleIntegrationsPage() {
  return (
    <>
      <ConsolePageHeader title="集成" description="外部服务与接线（与驾驶舱集成面板同源）" />
      <IntegrationsPage />
    </>
  );
}
