import Library from "./pages/Library";
import { Link, parseRoute, usePath } from "./router";

function Shell(props: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-full flex-col">
      <header className="flex min-h-12 items-center gap-6 border-b border-line bg-panel px-4">
        <Link to="/" className="flex min-h-11 items-center font-semibold tracking-wide">
          Scholia
        </Link>
        <span className="text-[13px] text-mute">Read the code. Check what the assistant says.</span>
      </header>
      <main className="min-h-0 flex-1">{props.children}</main>
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
    default:
      return (
        <Shell>
          <p className="p-6 text-mute">
            Nothing here. <Link to="/" className="text-cyan underline">Back to the library</Link>
          </p>
        </Shell>
      );
  }
}
