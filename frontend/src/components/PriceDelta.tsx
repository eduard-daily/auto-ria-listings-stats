import { formatMoney } from "../format";

/** Change of the listed price since we first saw it; nothing when it never moved. */
export function PriceDelta(props: {
  price: number | null;
  firstPrice: number | null;
  currency: string | null;
  changes: number;
}) {
  const { price, firstPrice, currency, changes } = props;
  if (price == null || firstPrice == null || price === firstPrice) return null;

  const delta = price - firstPrice;
  const percent = (delta / firstPrice) * 100;
  const sign = delta < 0 ? "−" : "+";
  return (
    <span
      className={`delta ${delta < 0 ? "delta-down" : "delta-up"}`}
      title={`${sign}${Math.abs(percent).toFixed(1)}% since first seen, ${changes} ${changes === 1 ? "change" : "changes"}`}
    >
      {delta < 0 ? "▼" : "▲"} {formatMoney(Math.abs(delta), currency)}
    </span>
  );
}
