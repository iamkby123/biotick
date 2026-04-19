"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  type ColumnDef,
} from "@tanstack/react-table";
import type { Company } from "@/lib/types";
import { formatMarketCap, formatPrice, formatPercent, cn } from "@/lib/utils";
import { ChevronRight } from "lucide-react";

interface CompanyTableProps {
  companies: Company[];
  onSort: (field: string) => void;
  sortBy: string;
  sortDir: string;
}

export default function CompanyTable({
  companies,
  onSort,
  sortBy,
  sortDir,
}: CompanyTableProps) {
  const columns = useMemo<ColumnDef<Company>[]>(
    () => [
      {
        accessorKey: "ticker",
        header: "Company",
        cell: ({ row }) => (
          <Link
            href={`/companies/${row.original.ticker}`}
            className="flex items-center gap-3 group"
          >
            <div className="w-8 h-8 rounded-md bg-surface-hover flex items-center justify-center text-[10px] font-bold text-accent shrink-0 group-hover:bg-accent/15 transition-colors">
              {row.original.ticker.slice(0, 3)}
            </div>
            <div className="min-w-0">
              <p className="font-semibold text-[13px] group-hover:text-accent transition-colors">
                {row.original.ticker}
              </p>
              <p className="text-[11px] text-muted truncate max-w-[180px]">
                {row.original.name}
              </p>
            </div>
          </Link>
        ),
        size: 240,
      },
      {
        accessorKey: "price",
        header: "Price",
        cell: ({ row }) => (
          <span className="font-mono text-[13px]">
            {formatPrice(row.original.price)}
          </span>
        ),
        size: 90,
      },
      {
        accessorKey: "price_change_pct",
        header: "Change",
        cell: ({ row }) => {
          const val = row.original.price_change_pct;
          return (
            <span
              className={cn(
                "font-mono text-[11px] font-semibold px-1.5 py-0.5 rounded",
                val !== null && val >= 0
                  ? "text-positive bg-positive/10"
                  : "text-negative bg-negative/10"
              )}
            >
              {formatPercent(val)}
            </span>
          );
        },
        size: 90,
      },
      {
        accessorKey: "market_cap",
        header: "Market Cap",
        cell: ({ row }) => (
          <span className="font-mono text-[13px] text-muted">
            {formatMarketCap(row.original.market_cap)}
          </span>
        ),
        size: 100,
      },
      {
        accessorKey: "sector",
        header: "Sector",
        cell: ({ row }) => (
          <span className="text-[11px] text-muted truncate max-w-[160px] block">
            {row.original.sector || "Biotech"}
          </span>
        ),
        size: 160,
      },
      {
        id: "arrow",
        header: "",
        cell: () => <ChevronRight className="w-3.5 h-3.5 text-muted/30" />,
        size: 30,
      },
    ],
    []
  );

  const table = useReactTable({
    data: companies,
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
  });

  const sortableColumns = ["ticker", "price", "price_change_pct", "market_cap", "sector"];

  return (
    <div className="rounded-lg border border-border overflow-x-auto">
      <table className="w-full">
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id} className="border-b border-border bg-surface/50">
              {headerGroup.headers.map((header) => {
                const columnId = header.column.id;
                const isSortable = sortableColumns.includes(columnId);
                const isActive = sortBy === columnId;

                return (
                  <th
                    key={header.id}
                    className={cn(
                      "px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-widest text-muted",
                      isSortable && "cursor-pointer hover:text-foreground select-none transition-colors"
                    )}
                    onClick={() => isSortable && onSort(columnId)}
                  >
                    <div className="flex items-center gap-1">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {isActive && (
                        <span className="text-accent">{sortDir === "asc" ? "\u25B2" : "\u25BC"}</span>
                      )}
                    </div>
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              className="border-b border-border last:border-b-0 hover:bg-surface/80 transition-colors cursor-pointer"
              onClick={() => {
                const ticker = row.original.ticker;
                window.location.href = `/companies/${ticker}`;
              }}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-4 py-3">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
          {companies.length === 0 && (
            <tr>
              <td colSpan={6} className="px-4 py-16 text-center text-sm text-muted">
                No companies found
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
