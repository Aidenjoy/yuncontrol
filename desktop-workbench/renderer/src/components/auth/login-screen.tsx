"use client"

import { BrandMark } from "@/components/brand-mark"

import { useState } from "react"
import { User, Lock, Eye, EyeOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Field, FieldError, FieldGroup, FieldLabel as Label } from "@/components/ui/field"
import { isValidEmail } from "@/features/auth/account-profile"
import { InputGroup, InputGroupAddon, InputGroupInput, InputGroupButton } from "@/components/ui/input-group"
import { AuthShell } from "./auth-shell"
import { useAuth } from "./auth-context"
import { useTranslations } from "next-intl"

/** Render the same direct account/password entry as Web inside the desktop window. */
export function LoginScreen() {
  const { login, signingIn: loading, error, clearError } = useAuth()
  const t = useTranslations("auth")
  const [localLogin, setLocalLogin] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const emailInvalid = Boolean(localLogin && email && !isValidEmail(email))

  /** Authenticate against the configured server; preserve the local administrator path. */
  const submit = async () => {
    if (loading || !(localLogin ? isValidEmail(email) : email.trim()) || !password) return
    await login({ email, password, utoken: !localLogin }).catch(() => undefined)
  }

  return (
    <AuthShell>
      <div className="mx-auto w-full max-w-sm">
        <div className="flex flex-col items-center gap-2 text-center mb-8">
          <h1 className="text-2xl font-bold tracking-tight">
            {t("login.titlePrefix")}{" "}
            <span className="aa-wordmark"><BrandMark className="mr-2" />云大师Agent</span>
          </h1>
          <p className="text-sm text-muted-foreground leading-relaxed">
            {localLogin ? t("login.description") : t("login.utokenDescription")}
          </p>
        </div>

        <form noValidate onSubmit={(event) => { event.preventDefault(); void submit() }}>
          <FieldGroup>
            <Field data-invalid={emailInvalid}>
              <Label htmlFor="login-email">{localLogin ? t("fields.email") : t("login.utokenAccount")}</Label>
              <InputGroup className="h-11 rounded-lg">
                <InputGroupAddon><User className="size-4" /></InputGroupAddon>
                <InputGroupInput
                  autoFocus
                  disabled={loading}
                  id="login-email"
                  value={email}
                  onChange={(event) => { setEmail(event.currentTarget.value); clearError() }}
                  placeholder={localLogin ? t("login.userPlaceholder") : t("login.utokenPlaceholder")}
                  type={localLogin ? "email" : "text"}
                  name="email"
                  inputMode={localLogin ? "email" : "text"}
                  autoCapitalize="none"
                  autoCorrect="off"
                  autoComplete="username"
                  spellCheck={false}
                  className="code-mono"
                  aria-invalid={emailInvalid}
                  aria-describedby={emailInvalid ? "login-email-error" : undefined}
                />
              </InputGroup>
              {emailInvalid ? <FieldError id="login-email-error">{t("login.invalidEmail")}</FieldError> : null}
            </Field>

            <Field>
              <Label htmlFor="login-password">{t("fields.password")}</Label>
              <InputGroup className="h-11 rounded-lg">
                <InputGroupAddon><Lock className="size-4" /></InputGroupAddon>
                <InputGroupInput
                  disabled={loading}
                  id="login-password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => { setPassword(event.currentTarget.value); clearError() }}
                  placeholder={t("login.passwordPlaceholder")}
                  autoComplete="current-password"
                  spellCheck={false}
                  className="code-mono"
                />
                <InputGroupAddon align="inline-end">
                  <InputGroupButton type="button" disabled={loading} onClick={() => setShowPassword((v) => !v)} aria-label={showPassword ? t("actions.hidePassword") : t("actions.showPassword")}>
                    {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </InputGroupButton>
                </InputGroupAddon>
              </InputGroup>
            </Field>

            <Button
              className="h-11 w-full font-medium"
              disabled={loading || !(localLogin ? isValidEmail(email) : email.trim()) || !password}
              type="submit"
            >
              {loading ? t("login.signingIn") : t("login.submitWithEnter")}
            </Button>

            {error ? <FieldError role="alert">{error}</FieldError> : null}

            <Button type="button" variant="ghost" disabled={loading} onClick={() => { setLocalLogin(!localLogin); setEmail(""); setPassword(""); clearError() }}>
              {t(localLogin ? "login.useUtoken" : "login.useLocal")}
            </Button>

          </FieldGroup>
        </form>
      </div>
    </AuthShell>
  )
}
