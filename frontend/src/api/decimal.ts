export function compareDecimal(left: string, right: string): number {
  const [leftUnits, rightUnits, scale] = align(left, right);
  void scale;
  return leftUnits < rightUnits ? -1 : leftUnits > rightUnits ? 1 : 0;
}

export function addDecimal(left: string, right: string): string {
  const [leftUnits, rightUnits, scale] = align(left, right);
  return canonical(leftUnits + rightUnits, scale);
}

function align(left: string, right: string): [bigint, bigint, number] {
  const a = parse(left);
  const b = parse(right);
  const scale = Math.max(a.scale, b.scale);
  return [a.units * 10n ** BigInt(scale - a.scale), b.units * 10n ** BigInt(scale - b.scale), scale];
}

function parse(value: string): { units: bigint; scale: number } {
  if (!/^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value)) throw new Error('Invalid decimal string');
  const negative = value.startsWith('-');
  const plain = negative ? value.slice(1) : value;
  const [whole, fraction = ''] = plain.split('.');
  const units = BigInt(`${whole}${fraction}` || '0');
  return { units: negative ? -units : units, scale: fraction.length };
}

function canonical(units: bigint, scale: number): string {
  const negative = units < 0n;
  let digits = (negative ? -units : units).toString().padStart(scale + 1, '0');
  let result = scale ? `${digits.slice(0, -scale)}.${digits.slice(-scale)}` : digits;
  if (scale) result = result.replace(/0+$/, '').replace(/\.$/, '');
  if (result === '') result = '0';
  return `${negative && result !== '0' ? '-' : ''}${result}`;
}

export function formatCurrencyDecimal(value: string, currency: string, fractionDigits = 2): string {
  const parsed = parse(value);
  const negative = parsed.units < 0n;
  const absolute = negative ? -parsed.units : parsed.units;
  const targetScale = fractionDigits;
  let rounded = absolute;
  if (parsed.scale > targetScale) {
    const divisor = 10n ** BigInt(parsed.scale - targetScale);
    rounded = absolute / divisor;
    if ((absolute % divisor) * 2n >= divisor) rounded += 1n;
  } else if (parsed.scale < targetScale) {
    rounded *= 10n ** BigInt(targetScale - parsed.scale);
  }
  const displayScale = 10n ** BigInt(targetScale);
  const whole = rounded / displayScale;
  const fraction = (rounded % displayScale).toString().padStart(targetScale, '0');
  const locale = new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: targetScale });
  const template = locale.formatToParts(negative ? -1 : 1);
  const integerParts = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).formatToParts(whole);
  const decimalMark = new Intl.NumberFormat(undefined, { minimumFractionDigits: targetScale, maximumFractionDigits: targetScale })
    .formatToParts(0).find((part) => part.type === 'decimal');
  const fractionPart = targetScale ? [{ type: 'fraction', value: fraction }] : [];
  const exactNumberParts = [...integerParts, ...(decimalMark ? [decimalMark] : []), ...fractionPart];
  const isNumeric = (type: string) => ['integer', 'group', 'decimal', 'fraction'].includes(type);
  let inserted = false;
  const result: string[] = [];
  for (const part of template) {
    if (isNumeric(part.type)) {
      if (!inserted) {
        result.push(...exactNumberParts.map((numberPart) => numberPart.value));
        inserted = true;
      }
    } else result.push(part.value);
  }
  return result.join('');
}
