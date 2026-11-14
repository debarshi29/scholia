import { lazy, Suspense, type ReactNode } from "react";
import { Loading } from "./components/ui";
import Library from "./pages/Library";
import Profiles from "./pages/Profiles";
import { Link, parseRoute, usePath } from "./router";

// Monaco is large; it loads only with the page that shows code.
const Session = lazy(() => import("./pages/Session"));
const Debrief = lazy(() => import("./pages/Debrief"));

// Each page brings its own top bar, as on the boards.
function Page(props: { fill?: boolean; children: ReactNode }) {
  return (
    <main className={props.fill ? "h-full overflow-hidden" : "min-h-full"}>
      <Suspense fallback={<Loading />}>{props.children}</Suspense>
    </main>
  );
}

export default function App() {
  const route = parseRoute(usePath());
  switch (route.page) {
    case "library":
      return (
        <Page>
          <Library />
        </Page>
      );
    case "profiles":
      return (
        <Page>
          <Profiles />
        </Page>
      );
    case "session":
      return (
        <Page fill>
          <Session id={route.id} />
        </Page>
      );
    case "debrief":
      return (
        <Page>
          <Debrief id={route.id} />
        </Page>
      );
    default:
      return (
        <Page>
          <p className="p-6 text-mute">
            Nothing here.{" "}
            <Link to="/" className="text-cyan underline">
              Back to the library
            </Link>
          </p>
        </Page>
      );
  }
}
