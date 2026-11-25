import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

async function bootstrap() {
  if (import.meta.env.DEV && import.meta.env.VITE_API_MODE === "mock") {
    const { installMockApi } = await import("./mocks");
    installMockApi();
  }
  createRoot(document.getElementById("root")!).render(
    <BrowserRouter basename="/">
      <App />
    </BrowserRouter>,
  );
}

void bootstrap();
