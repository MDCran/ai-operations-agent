import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { BriefcaseBusiness, ShieldCheck } from 'lucide-react'
import { write, setCsrf } from '../services/api'
import { Button } from '../components/ui/button'
import { ErrorState } from '../components/shared'

const schema = z.object({
  email: z.email(),
  password: z.string().min(1),
  organization_id: z.string().optional(),
})
export function Login({ onSuccess }: { onSuccess: () => void }) {
  const [error, setError] = useState<unknown>()
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) })
  return (
    <div className="login-page">
      <div className="login-intro">
        <div className="brand">
          <span className="brand-mark">
            <BriefcaseBusiness size={21} />
          </span>{' '}
          Operations Desk
        </div>
        <div>
          <span className="eyebrow">A BETTER WAY TO RUN THE DAY</span>
          <h1>
            Your team’s work.
            <br />
            One connected workspace.
          </h1>
          <p>
            Bring support, scheduling and company knowledge into one place.
            Keep a person in control of every important action.
          </p>
          <div className="login-proof">
            <ShieldCheck size={20} />
            <span>
              Authorized actions. Human approvals. A complete audit trail.
            </span>
          </div>
        </div>
        <small>Operations Desk · Open source</small>
      </div>
      <div className="login-form-wrap">
        <form
          onSubmit={handleSubmit(async (values) => {
            try {
              setError(undefined)
              const body = {
                ...values,
                organization_id: values.organization_id || undefined,
              }
              const result = await write<{ csrf_token: string }>(
                '/auth/login',
                body,
              )
              setCsrf(result.csrf_token)
              onSuccess()
            } catch (e) {
              setError(e)
            }
          })}
        >
          <span className="eyebrow">WELCOME BACK</span>
          <h2>Sign in to your workspace</h2>
          <p>Use the account configured for your organization.</p>
          <label>
            Email address
            <input
              autoComplete="username"
              type="email"
              placeholder="you@company.com"
              {...register('email')}
            />
          </label>
          {errors.email && (
            <small className="field-error">Enter a valid email.</small>
          )}
          <label>
            Password
            <input
              autoComplete="current-password"
              type="password"
              {...register('password')}
            />
          </label>
          <details>
            <summary>Multiple organizations?</summary>
            <label>
              Organization ID
              <input {...register('organization_id')} />
            </label>
          </details>
          {error !== undefined && <ErrorState error={error} />}
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Signing in…' : 'Sign in'}
          </Button>
          <small className="login-note">
            For a local demo, use DEMO_EMAIL and DEMO_PASSWORD from your
            environment configuration.
          </small>
        </form>
      </div>
    </div>
  )
}
