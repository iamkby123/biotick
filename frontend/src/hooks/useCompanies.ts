"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchAPI } from "@/lib/api";
import type { CompanyListResponse, Company } from "@/lib/types";

interface UseCompaniesParams {
  search?: string;
  exchange?: string;
  minMarketCap?: number;
  maxMarketCap?: number;
  sector?: string;
  minRunway?: number;
  maxRunway?: number;
  highestPhase?: string;
  profitability?: string;
  hasCatalystDays?: number;
  sortBy?: string;
  sortDir?: string;
  page?: number;
  perPage?: number;
}

export function useCompanies(params: UseCompaniesParams = {}) {
  const {
    search,
    exchange,
    minMarketCap,
    maxMarketCap,
    sector,
    minRunway,
    maxRunway,
    highestPhase,
    profitability,
    hasCatalystDays,
    sortBy = "market_cap",
    sortDir = "desc",
    page = 1,
    perPage = 50,
  } = params;

  const queryString = new URLSearchParams();
  if (search) queryString.set("search", search);
  if (exchange) queryString.set("exchange", exchange);
  if (minMarketCap !== undefined) queryString.set("min_market_cap", String(minMarketCap));
  if (maxMarketCap !== undefined) queryString.set("max_market_cap", String(maxMarketCap));
  if (sector) queryString.set("sector", sector);
  if (minRunway !== undefined) queryString.set("min_runway_months", String(minRunway));
  if (maxRunway !== undefined) queryString.set("max_runway_months", String(maxRunway));
  if (highestPhase) queryString.set("highest_phase", highestPhase);
  if (profitability) queryString.set("profitability", profitability);
  if (hasCatalystDays !== undefined) queryString.set("has_catalyst_days", String(hasCatalystDays));
  queryString.set("sort_by", sortBy);
  queryString.set("sort_dir", sortDir);
  queryString.set("page", String(page));
  queryString.set("per_page", String(perPage));

  return useQuery<CompanyListResponse>({
    queryKey: ["companies", params],
    queryFn: () => fetchAPI(`/companies?${queryString.toString()}`),
  });
}

export function useCompany(ticker: string) {
  return useQuery<Company>({
    queryKey: ["company", ticker],
    queryFn: () => fetchAPI(`/companies/${ticker}`),
    enabled: !!ticker,
  });
}
