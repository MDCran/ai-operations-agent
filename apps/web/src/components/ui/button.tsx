import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export const cn = (...inputs: Parameters<typeof clsx>) =>
  twMerge(clsx(...inputs))
const variants = cva('btn', {
  variants: {
    variant: {
      default: 'btn-primary',
      outline: 'btn-outline',
      ghost: 'btn-ghost',
      destructive: 'btn-danger',
    },
  },
  defaultVariants: { variant: 'default' },
})
export function Button({
  className,
  variant,
  asChild = false,
  ...props
}: React.ComponentProps<'button'> &
  VariantProps<typeof variants> & { asChild?: boolean }) {
  const Component = asChild ? Slot : 'button'
  return (
    <Component className={cn(variants({ variant }), className)} {...props} />
  )
}
