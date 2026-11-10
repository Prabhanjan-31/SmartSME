import { Link } from "react-router-dom";
import { useApi } from "@/lib/api";
import { PageHeader, PageState, SectionCard, StatCard, EmptyState } from "@/components/ui/misc";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { InfoTip } from "@/components/ui/info-tip";
import { buttonVariants } from "@/components/ui/button";
import { PaymentBadge } from "@/components/Status";
import { Icon } from "@/components/Icon";
import { RevenueChart } from "@/components/RevenueChart";
import { compactMoney, formatDate, money } from "@/lib/utils";
import { type Health, type HealthScore, healthColor, healthLabel, healthTone } from "@/lib/health";

interface Row {
  id: string;
  date: string;
  partyName: string | null;
  total: number;
  paymentStatus: string;
  overdue: boolean;
  invoiceNumber?: string;
  referenceNumber?: string;
}

interface DashboardData {
  totals: {
    sales: number;
    purchases: number;
    expenses: number;
    receivable: number;
    payable: number;
    inventoryValue: number;
    grossProfit: number;
  };
  health: Health;
  lowStock: { id: string; name: string; stock: number; unit: string; lowStockThreshold: number }[];
  recentSales: Row[];
  recentPurchases: Row[];
  business: { name: string; currency: string };
}

function HealthRow({ label, score }: { label: string; score: HealthScore }) {
  const color = healthColor(score);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="text-muted-foreground">{label}</span>
        {score === null ? (
          <span className="text-xs text-muted-foreground">No data yet</span>
        ) : (
          <span className="font-medium tabular-nums">{score}</span>
        )}
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        {score !== null && color && (
          <div
            className="h-full rounded-full"
            style={{ width: `${score}%`, backgroundColor: `var(${color})` }}
          />
        )}
      </div>
    </div>
  );
}

export function Dashboard() {
  const { data, loading, error } = useApi<DashboardData>("/dashboard");
  if (!data) return <PageState loading={loading} error={error} />;

  const cur = data.business.currency;
  const o = data.totals;

  return (
    <div className="space-y-6">
      <PageHeader title="Dashboard" description={`Here's how ${data.business.name} is doing.`}>
        <Link to="/input" className={buttonVariants()}>
          <Icon name="input" size={16} /> Smart input
        </Link>
      </PageHeader>

      {/* KPIs, each linking through to the matching page */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <StatCard
          label="Total sales"
          value={compactMoney(o.sales, cur)}
          icon={<Icon name="sales" />}
          tone="primary"
          to="/sales"
        />
        <StatCard
          label="Purchases"
          value={compactMoney(o.purchases, cur)}
          icon={<Icon name="purchases" />}
          tone="info"
          to="/purchases"
        />
        <StatCard
          label="Expenses"
          value={compactMoney(o.expenses, cur)}
          icon={<Icon name="expenses" />}
          tone="warning"
          to="/expenses"
        />
        <StatCard
          label="Inventory"
          value={compactMoney(o.inventoryValue, cur)}
          icon={<Icon name="box" />}
          tone="info"
          to="/products"
        />
        <StatCard
          label="Receivable"
          value={compactMoney(o.receivable, cur)}
          icon={<Icon name="trendingUp" />}
          tone="success"
          to="/parties?type=customer"
        />
        <StatCard
          label="Payable"
          value={compactMoney(o.payable, cur)}
          icon={<Icon name="trendingDown" />}
          tone="destructive"
          to="/parties?type=supplier"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>Revenue trend</CardTitle>
              <CardDescription>Gross profit {money(o.grossProfit, cur)}</CardDescription>
            </div>
            <Link to="/reports" className="text-sm text-link hover:underline">
              Reports →
            </Link>
          </CardHeader>
          <CardContent>
            <RevenueChart currency={cur} initialDays={30} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              Business health
              <InfoTip label="About the business health score">
                A mark out of 100 built from four parts: cash flow (30%), profitability (30%),
                revenue (25%) and inventory (15%). 70 and up is Healthy, 40 to 69 is Fair, below 40
                is At risk. One weak part holds the overall mark down, and a part with nothing to
                measure yet shows no number.
              </InfoTip>
            </CardTitle>
            <CardDescription>Overall score</CardDescription>
          </CardHeader>
          <CardContent>
            {data.health.overall === null ? (
              <div className="mb-4">
                <div className="text-lg font-semibold">Not enough data yet</div>
                <p className="text-sm text-muted-foreground">
                  The score appears once a few weeks of sales, purchases and expenses are recorded.
                </p>
              </div>
            ) : (
              <div className="mb-4 flex items-end gap-2">
                <span className="text-4xl font-semibold tracking-tight">{data.health.overall}</span>
                <span className="mb-1 text-sm text-muted-foreground">/ 100</span>
                <Badge className="mb-1 ml-auto" tone={healthTone(data.health.overall)}>
                  {healthLabel(data.health.overall)}
                </Badge>
              </div>
            )}
            <div className="space-y-2.5">
              <HealthRow label="Cash flow" score={data.health.cashFlow} />
              <HealthRow label="Profitability" score={data.health.profitability} />
              <HealthRow label="Revenue" score={data.health.revenue} />
              <HealthRow label="Inventory" score={data.health.inventory} />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent activity: sales and purchases side by side */}
      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard
          title="Recent sales"
          action={
            <Link to="/sales" className="text-sm text-link hover:underline">
              View all
            </Link>
          }
        >
          {data.recentSales.length === 0 ? (
            <div className="p-6">
              <EmptyState
                icon={<Icon name="sales" />}
                title="No sales yet"
                description="Create one from Smart Input or the Sales page."
              />
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {data.recentSales.map((s) => (
                <li key={s.id} className="flex items-center gap-3 p-4">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                    <Icon name="sales" size={16} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <Link to={`/sales/${s.id}`} className="font-medium hover:text-link">
                      {s.invoiceNumber}
                    </Link>
                    <div className="text-xs text-muted-foreground">
                      {s.partyName ?? "Walk-in"} · {formatDate(s.date)}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-medium tabular-nums">{money(s.total, cur)}</div>
                    <PaymentBadge status={s.paymentStatus} overdue={s.overdue} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        <SectionCard
          title="Recent purchases"
          action={
            <Link to="/purchases" className="text-sm text-link hover:underline">
              View all
            </Link>
          }
        >
          {data.recentPurchases.length === 0 ? (
            <div className="p-6">
              <EmptyState
                icon={<Icon name="purchases" />}
                title="No purchases yet"
                description="Record a supplier bill from Smart Input or the Purchases page."
              />
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {data.recentPurchases.map((p) => (
                <li key={p.id} className="flex items-center gap-3 p-4">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-info/15 text-info">
                    <Icon name="purchases" size={16} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="font-medium">{p.referenceNumber}</div>
                    <div className="text-xs text-muted-foreground">
                      {p.partyName ?? "Supplier"} · {formatDate(p.date)}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-medium tabular-nums">{money(p.total, cur)}</div>
                    <PaymentBadge status={p.paymentStatus} overdue={p.overdue} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>

      <SectionCard
        title="Needs attention"
        info="Products whose stock is at or below their low-stock threshold. Each product has its own threshold, set on the Products page."
        action={
          <Link to="/notifications" className="text-sm text-link hover:underline">
            All alerts
          </Link>
        }
      >
        {data.lowStock.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon={<Icon name="check" />}
              title="All good"
              description="No low-stock items right now."
            />
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {data.lowStock.slice(0, 6).map((p) => (
              <li key={p.id} className="flex items-center gap-3 p-3">
                <span
                  className={
                    p.stock <= 0
                      ? "flex h-8 w-8 items-center justify-center rounded-lg bg-destructive/15 text-destructive"
                      : "flex h-8 w-8 items-center justify-center rounded-lg bg-warning/15 text-warning"
                  }
                >
                  <Icon name="alert" size={15} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{p.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {p.stock} {p.unit} left · threshold {p.lowStockThreshold}
                  </div>
                </div>
                {p.stock <= 0 ? (
                  <Badge tone="destructive">Out</Badge>
                ) : (
                  <Badge tone="warning">Low</Badge>
                )}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}
