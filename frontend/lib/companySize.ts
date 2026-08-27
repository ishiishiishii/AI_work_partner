const BADGE_CLASS_BY_SIZE: Record<string, string> = {
  中小企業: "badge--size-small",
  中堅企業: "badge--size-mid",
  大企業: "badge--size-large",
};

export function companySizeBadgeClass(companySizeName: string): string {
  return BADGE_CLASS_BY_SIZE[companySizeName] ?? "";
}
