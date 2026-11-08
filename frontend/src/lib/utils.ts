import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNumber(n: number | null | undefined) {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("en-US");
}

export function formatPct(n: number | null | undefined) {
  if (n === null || n === undefined) return "—";
  return `${n.toFixed(1)}%`;
}

/** Strips anything that isn't a digit, keeping a leading "+" if the user
 * typed one first — so pasting/typing letters, spaces, or dashes never
 * reaches state, matching what the backend itself requires (see
 * backend/app/utils/phone.py's PHONE_FORMAT_RE). */
export function sanitizePhoneInput(value: string): string {
  const hasLeadingPlus = value.startsWith("+");
  const digits = value.replace(/\D/g, "");
  return hasLeadingPlus ? `+${digits}` : digits;
}

const PHONE_RE = /^\+?\d{7,15}$/;
export function isValidPhone(value: string): boolean {
  return PHONE_RE.test(value.trim());
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export function isValidEmail(value: string): boolean {
  return EMAIL_RE.test(value.trim());
}

export function positionLabel(name: string) {
  return name
    .split("_")
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

/** Shared status→badge-variant mapping for a FormSubmission, used anywhere a
 * submission list is rendered (moderation queue, campaign-manager and
 * aspirant submission views). */
export const SUBMISSION_STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "neutral"> = {
  auto_approved: "success",
  manually_approved: "success",
  pending_review: "warning",
  rejected: "destructive",
  duplicate: "destructive",
  draft: "neutral",
};
