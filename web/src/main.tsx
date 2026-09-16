/** The mount. Everything else is a component. */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import "./style/tokens.css";
import "./style/base.css";
import "./style/shell.css";
import "./style/parts.css";
import "./style/list.css";
import "./style/thread.css";
import "./style/composer.css";
import "./style/form.css";

const el = document.getElementById("root")! as HTMLElement & { _root?: ReturnType<typeof createRoot> };
el._root ??= createRoot(el);
el._root.render(<StrictMode><App /></StrictMode>);
