import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./index.css";

const config = JSON.parse(
  document.getElementById("chat-config").textContent,
);

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App config={config} />
  </React.StrictMode>,
);
