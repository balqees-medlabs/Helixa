export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-4 px-6">
      <p className="text-sm font-medium uppercase tracking-wide text-brand">Medlabs Genomics</p>
      <h1 className="text-4xl font-semibold tracking-tight">Helixa</h1>
      <p className="max-w-xl text-muted-foreground">
        Frontend setup is ready. Sign-in, role dashboards, and the sample workflow arrive in the
        next slices.
      </p>
    </main>
  );
}
