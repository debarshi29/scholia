import { lazy, Suspense, type ReactNode } from "react";
import { Loading } from "./components/ui";
import Library from "./pages/Library";
import { Link, parseRoute, usePath } from "./router";

// Monaco is large; it loads only with the pages that show code.
const Session = lazy(() => import("./pages/Session"));
const Debrief = lazy(() => import("./pages/Debrief"));

function Shell(props: { fill?: boolean; children: ReactNode }) {
  return (
    <div className={`flex flex-col ${props.fill ? "h-full" : "min-h-full"}`}>
      <header className="flex min-h-12 shrink-0 items-center gap-6 border-b border-line bg-panel px-4">
        <Link to="/" className="flex min-h-11 items-center font-semibold tracking-wide">
          Scholia
        </Link>
        <span className="text-[13px] text-mute">Read the code. Check what the assistant says.</span>
      </header>
      <main className={`min-h-0 flex-1 ${props.fill ? "overflow-hidden" : ""}`}>
        <Suspense fallback={<Loading />}>{props.children}</Suspense>
      </main>
    </div>
  );
}

export default function App() {
  const route = parseRoute(usePath());
  switch (route.page) {
    case "library":
      return (
        <Shell>
          <Library />
        </Shell>
      );
    case "session":
      return (
        <Shell fill>
          <Session id={route.id} />
        </Shell>
      );
    case "debrief":
      return (
        <Shell>
          <Debrief id={route.id} />
        </Shell>
      );
    default:
      return (
        <Shell>
          <p className="p-6 text-mute">
            Nothing here.{" "}
            <Link to="/" className="text-cyan underline">
              Back to the library
            </Link>
          </p>
        </Shell>
      );
  }
}
