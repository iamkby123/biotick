import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatMarketCap(value: number | null): string {
  if (value === null || value === undefined) return "N/A";
  if (value >= 1e12) return `$${(value / 1e12).toFixed(1)}T`;
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
  if (value >= 1e3) return `$${(value / 1e3).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
}

export function formatPrice(value: number | null): string {
  if (value === null || value === undefined) return "N/A";
  return `$${value.toFixed(2)}`;
}

export function formatPercent(value: number | null): string {
  if (value === null || value === undefined) return "N/A";
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

export function formatNumber(value: number | null): string {
  if (value === null || value === undefined) return "N/A";
  return value.toLocaleString();
}

const MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function formatCatalystDate(
  dateStr: string | null,
  precision: string | null
): string {
  if (!dateStr) return "TBD";

  const parts = dateStr.split("-");
  const year = parts[0];
  const month = parseInt(parts[1], 10);
  const day = parseInt(parts[2], 10);

  switch (precision) {
    case "QUARTER": {
      const q = Math.ceil(month / 3);
      return `Q${q} ${year}`;
    }
    case "EXACT":
      return `${MONTH_SHORT[month - 1]} ${day}, ${year}`;
    case "MONTH":
    default:
      return `${MONTH_SHORT[month - 1]} ${year}`;
  }
}
