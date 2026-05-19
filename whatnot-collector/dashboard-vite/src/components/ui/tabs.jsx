import * as TabsPrimitive from '@radix-ui/react-tabs';
import { cn } from '../../lib/utils';

export const Tabs = TabsPrimitive.Root;
export const TabsContent = TabsPrimitive.Content;

export function TabsList({ className, ...props }) {
  return <TabsPrimitive.List className={cn('flex items-center gap-1 border-b border-slate-200', className)} {...props} />;
}

export function TabsTrigger({ active, className, value, ...props }) {
  if (value) {
    return (
      <TabsPrimitive.Trigger
        value={value}
        className={cn(
          'relative px-3 py-2 text-sm font-medium text-slate-500 transition-colors hover:text-slate-950 data-[state=active]:text-slate-950 data-[state=active]:after:absolute data-[state=active]:after:inset-x-0 data-[state=active]:after:-bottom-px data-[state=active]:after:h-0.5 data-[state=active]:after:bg-[#635bff]',
          className
        )}
        {...props}
      />
    );
  }
  return (
    <button
      type="button"
      className={cn(
        'relative px-3 py-2 text-sm font-medium text-slate-500 transition-colors hover:text-slate-950',
        active && 'text-slate-950 after:absolute after:inset-x-0 after:-bottom-px after:h-0.5 after:bg-[#635bff]',
        className,
      )}
      {...props}
    />
  );
}
