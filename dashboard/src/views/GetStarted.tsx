import { IconActivity, IconBank, IconScan } from "../icons";

/** What to do first when nothing has been scanned: three steps, in order. */
export function GetStarted() {
  const steps = [
    {
      icon: <IconScan size={20} />,
      title: "Scan a project",
      text: "Paste a GitHub link or upload a project folder. Every endpoint is found in the code and checked against the specification and history.",
      href: "#scan",
      action: "New scan",
    },
    {
      icon: <IconActivity size={20} />,
      title: "Import its access logs",
      text: "Usage turns suspected zombies into proven ones. Logs from nginx, a load balancer or an API gateway, as they are.",
      href: null,
      action: "After the first scan",
    },
    {
      icon: <IconBank size={20} />,
      title: "Explore the demo bank",
      text: "A simulated bank with all six evidence sources: classification, the removal gate and Safe Kill end to end.",
      href: "#results/demo/overview",
      action: "Open the demo",
    },
  ];
  return (
    <ol className="get-started">
      {steps.map((s, i) => (
        <li key={s.title}>
          <span className="gs-icon">{s.icon}</span>
          <div className="gs-text">
            <span className="gs-no">Step {i + 1}</span>
            <strong>{s.title}</strong>
            <p>{s.text}</p>
          </div>
          {s.href ? (
            <a className={i === 0 ? "btn" : "btn secondary"} href={s.href}>
              {s.action}
            </a>
          ) : (
            <span className="muted small">{s.action}</span>
          )}
        </li>
      ))}
    </ol>
  );
}
