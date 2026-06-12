"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import {
  LayoutDashboard,
  PieChart,
  TrendingUp,
  Settings,
  Activity,
} from "lucide-react";

interface NavItem {
  label: string;
  href: string;
  icon: typeof LayoutDashboard;
}

const navItems: NavItem[] = [
  { label: "Dashboard", href: "/", icon: LayoutDashboard },
  { label: "Portfolio", href: "/portfolio", icon: PieChart },
  { label: "Performance", href: "/performance", icon: TrendingUp },
  { label: "Settings", href: "/settings", icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      className="fixed left-0 top-0 z-40 h-screen w-64 bg-surface-card border-r border-surface-border flex flex-col"
      role="navigation"
      aria-label="Main navigation"
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-surface-border">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-crypto-blue to-crypto-green flex items-center justify-center">
          <Activity className="h-4 w-4 text-white" aria-hidden="true" />
        </div>
        <div>
          <h1 className="text-base font-bold text-white">CryptoAI</h1>
          <p className="text-[10px] text-gray-500 leading-tight">Trading Platform</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1" aria-label="Sidebar">
        {navItems.map((item) => {
          const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all",
                "focus:outline-none focus:ring-2 focus:ring-crypto-blue focus:ring-offset-2 focus:ring-offset-surface-card",
                isActive
                  ? "bg-crypto-blue/10 text-crypto-blue"
                  : "text-gray-400 hover:text-gray-200 hover:bg-surface-hover"
              )}
              aria-current={isActive ? "page" : undefined}
            >
              <item.icon className="h-4.5 w-4.5" aria-hidden="true" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Status indicator */}
      <div className="px-6 py-4 border-t border-surface-border">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-crypto-green opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-crypto-green" />
          </span>
          <span className="text-xs text-gray-400">System Operational</span>
        </div>
      </div>
    </aside>
  );
}
