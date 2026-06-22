const stackItems = [
  { label: "Python", detail: "notebook, pandas, scikit-learn" },
  { label: "React", detail: "Vite + JavaScript workspace" },
  { label: "Spring", detail: "Java 21 + Spring Boot API" },
  { label: "R", detail: "tidyverse, ggplot2, IRkernel" },
];

export default function App() {
  return (
    <main className="shell">
      <section className="workspace">
        <div className="summary">
          <p className="eyebrow">SBS DataScience</p>
          <h1>Learning workspace</h1>
          <p>
            Data analysis notebooks, a React practice surface, and a Spring Boot API are
            separated but runnable from one repository.
          </p>
        </div>

        <div className="stack-grid" aria-label="Configured development stack">
          {stackItems.map((item) => (
            <article className="stack-card" key={item.label}>
              <strong>{item.label}</strong>
              <span>{item.detail}</span>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
