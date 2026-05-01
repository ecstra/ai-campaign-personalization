import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function getTimezoneAbbr(): string {
  const date = new Date()
  const parts = new Intl.DateTimeFormat(undefined, { timeZoneName: "short" }).formatToParts(date)
  const tzPart = parts.find(p => p.type === "timeZoneName")?.value || ""
  if (/^[A-Z]{2,5}$/.test(tzPart)) return tzPart

  const longParts = new Intl.DateTimeFormat("en-US", { timeZoneName: "long" }).formatToParts(date)
  const longTz = longParts.find(p => p.type === "timeZoneName")?.value || ""

  const tzMappings: Record<string, string> = {
    "Pacific Standard Time": "PST", "Pacific Daylight Time": "PDT",
    "Mountain Standard Time": "MST", "Mountain Daylight Time": "MDT",
    "Central Standard Time": "CST", "Central Daylight Time": "CDT",
    "Eastern Standard Time": "EST", "Eastern Daylight Time": "EDT",
    "Greenwich Mean Time": "GMT", "Coordinated Universal Time": "UTC",
    "British Summer Time": "BST", "Central European Time": "CET",
    "Central European Summer Time": "CEST", "India Standard Time": "IST",
    "Indian Standard Time": "IST", "Japan Standard Time": "JST",
    "China Standard Time": "CST", "Singapore Time": "SGT",
    "Australian Eastern Standard Time": "AEST", "Australian Eastern Daylight Time": "AEDT",
    "New Zealand Standard Time": "NZST", "New Zealand Daylight Time": "NZDT",
  }

  return tzMappings[longTz] || tzPart
}

export function formatTime(dateString: string | null): { time: string; timezone: string } | null {
  if (!dateString) return null
  const date = new Date(dateString)
  const time = date.toLocaleString(undefined, { hour: "numeric", minute: "2-digit" })
  return { time, timezone: getTimezoneAbbr() }
}
