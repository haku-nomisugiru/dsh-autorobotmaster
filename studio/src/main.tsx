import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { loadInterfaceFonts } from "./interfaceFonts";
import "./styles.css";
import "./design.css";
void loadInterfaceFonts().finally(() => {
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
});
