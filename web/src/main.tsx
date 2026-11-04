/** The mount. Everything else is a component. */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import "./style/tokens.css";
import "./style/base.css";
import "./style/shell.css";
import "./style/cards.css";
import "./style/home.css";
import "./style/queue.css";
import "./style/desk.css";
import "./style/chat.css";
import "./style/composer.css";
import "./style/parts.css";
import "./style/form.css";
import "./style/assistant.css";
import "./style/calendar.css";
import "./style/grid.css";

const el = document.getElementById("root")! as HTMLElement & { _root?: ReturnType<typeof createRoot> };
el._root ??= createRoot(el);
el._root.render(<StrictMode><App /></StrictMode>);
