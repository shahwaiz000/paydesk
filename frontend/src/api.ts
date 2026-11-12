// Talks to the PayDesk backend (FastAPI on port 8001).

export const API_URL = "http://localhost:8001";
const TOKEN_KEY = "paydesk_token";
export const DISPUTES_CHANGED = "paydesk:disputes-changed"; // tells the header badge to refresh

export type Role = "accountant" | "finance_manager" | "cashier" | "driver";

export interface User {
  id: number;
  username: string;
  full_name: string;
  role: Role;
  station_code: string | null;
  station_name: string | null;
  driver_id: string | null;
}

export const ROLE_LABELS: Record<Role, string> = {
  accountant: "Payroll Accountant",
  finance_manager: "Finance Manager",
  cashier: "Station Cashier",
  driver: "Driver",
};

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // storage not available - login just won't survive a page refresh
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let res: Response;
  try {
    res = await fetch(API_URL + path, { ...options, headers });
  } catch {
    throw new ApiError(0, "Can't reach the PayDesk server. Is Window 3 (backend) running?");
  }

  if (!res.ok) {
    let message = res.statusText;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") message = data.detail;
    } catch {
      // response was not JSON
    }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

// Download a file (Excel etc.) that needs the login token.
export async function downloadFile(path: string, filename: string) {
  const token = getToken();
  let res: Response;
  try {
    res = await fetch(API_URL + path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  } catch {
    throw new ApiError(0, "Can't reach the PayDesk server. Is Window 3 (backend) running?");
  }
  if (!res.ok) throw new ApiError(res.status, "Download failed");
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
