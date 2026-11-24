const DATE_TIME = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeStyle: "short",
});

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return DATE_TIME.format(date);
}

export function formatDurationHours(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) {
    return "—";
  }
  if (hours < 24) {
    return `${hours.toFixed(1)} h`;
  }
  const days = Math.floor(hours / 24);
  const remainder = Math.round(hours - days * 24);
  return remainder ? `${days} d ${remainder} h` : `${days} d`;
}
