import { cn } from '../../lib/utils';

export function Table({ className, ...props }) {
  return <table className={cn('w-full caption-bottom text-sm', className)} {...props} />;
}

export function TableHeader({ className, ...props }) {
  return <thead className={cn('[&_tr]:border-b', className)} {...props} />;
}

export function TableBody({ className, ...props }) {
  return <tbody className={cn('[&_tr:last-child]:border-0', className)} {...props} />;
}

export function TableRow({ className, ...props }) {
  return <tr className={cn('border-b border-slate-100 transition-colors hover:bg-slate-50/70', className)} {...props} />;
}

export function TableHead({ className, ...props }) {
  return <th className={cn('h-10 px-4 text-left align-middle text-xs font-semibold uppercase tracking-wide text-slate-500', className)} {...props} />;
}

export function TableCell({ className, ...props }) {
  return <td className={cn('px-4 py-3 align-middle text-slate-700', className)} {...props} />;
}
