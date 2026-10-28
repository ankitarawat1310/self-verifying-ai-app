import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import PlatformGate from "./components/PlatformGate.jsx";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <PlatformGate>
        <App />
      </PlatformGate>
    </BrowserRouter>
  </React.StrictMode>
);
