import { Slot } from '@radix-ui/react-slot';
import { cva } from 'class-variance-authority';
import { cn } from '../../lib/utils';

export const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[9px] text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6C47FF] focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'border border-[#6C47FF] bg-[#6C47FF] text-white shadow-sm hover:bg-[#4C32D9] hover:border-[#4C32D9]',
        secondary: 'border border-[#EAE6FF] bg-white text-[#4B5563] shadow-sm hover:bg-[#FDFCFF]',
        outline: 'border border-[#EAE6FF] bg-white text-[#1A1035] hover:bg-[#FDFCFF]',
        ghost: 'text-[#6B7280] hover:bg-[#F3F0FF] hover:text-[#6C47FF]',
        danger: 'border border-[#ffd7df] bg-white text-[#DC2626] hover:bg-[#FFECEC]',
        success: 'border border-[#d6f2e5] bg-[#E8F8F1] text-[#0F9F6E] hover:bg-[#dff5eb]',
      },
      size: {
        sm: 'h-8 px-3 text-xs',
        md: 'h-9 px-3.5',
        lg: 'h-10 px-4',
        icon: 'h-9 w-9',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'md',
    },
  }
);

export function Button({ className, variant = 'default', size = 'md', asChild = false, ...props }) {
  const Comp = asChild ? Slot : 'button';
  return (
    <Comp
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}
