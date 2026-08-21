type StatusPanelProps = {
  title: string;
  ok: boolean;
  body: string;
};

export function StatusPanel({ title, ok, body }: StatusPanelProps) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      <pre className={`status ${ok ? "ok" : "warn"}`}>{body}</pre>
    </section>
  );
}
