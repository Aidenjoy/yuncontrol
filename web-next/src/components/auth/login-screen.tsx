"use client"

import { useState } from "react"
import { Globe, User, Lock, Eye, EyeOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Field,
  FieldError,
  FieldGroup,
  FieldLabel as Label,
} from "@/components/ui/field"
import { isValidEmail } from "@/features/auth/account-profile"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
  InputGroupButton,
} from "@/components/ui/input-group"
import { AuthShell } from "./auth-shell"
import { useAuth } from "./auth-context"
import { PrivacyNotice } from "./privacy-notice"
import { UtokenRegisterScreen } from "./utoken-register-screen"
import { useLocalAdminLogin } from "@/features/auth/use-local-admin-login"
import { useTranslations } from "next-intl"

export function LoginScreen() {
  const {
    navigate,
    login,
    loading,
    error,
    oauthEnabled,
    oauthProviderLabel,
    passwordResetEnabled,
    startOAuth,
  } = useAuth()
  const t = useTranslations("auth")
  const localLogin = useLocalAdminLogin()
  const [registering, setRegistering] = useState(false)
  const [registered, setRegistered] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const emailInvalid = Boolean(localLogin && email && !isValidEmail(email))

  const submit = async () => {
    if (
      loading ||
      !(localLogin ? isValidEmail(email) : email.trim()) ||
      !password
    )
      return
    await login({ email, password, utoken: !localLogin }).catch(() => undefined)
  }

  if (registering && !localLogin)
    return (
      <UtokenRegisterScreen
        onBack={(success) => {
          setRegistering(false)
          setRegistered(Boolean(success))
        }}
      />
    )

  return (
    <AuthShell>
      <div className="flex flex-col items-center gap-2 text-center mb-8">
        <h1 className="text-2xl font-bold tracking-tight">
          {t("login.titlePrefix")}
        </h1>
        <p className="text-sm text-muted-foreground leading-relaxed">
          {localLogin ? t("login.description") : t("login.utokenDescription")}
        </p>
      </div>

      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        <FieldGroup>
          <Field data-invalid={emailInvalid}>
            <Label htmlFor="login-email">
              {localLogin ? t("fields.email") : t("login.utokenAccount")}
            </Label>
            <InputGroup className="h-11 rounded-lg">
              <InputGroupAddon>
                <User className="size-4" />
              </InputGroupAddon>
              <InputGroupInput
                id="login-email"
                value={email}
                onChange={(event) => setEmail(event.currentTarget.value)}
                placeholder={
                  localLogin
                    ? t("login.userPlaceholder")
                    : t("login.utokenPlaceholder")
                }
                type={localLogin ? "email" : "text"}
                name="email"
                inputMode={localLogin ? "email" : "text"}
                autoCapitalize="none"
                autoCorrect="off"
                autoComplete="username"
                spellCheck={false}
                className="code-mono"
                aria-invalid={emailInvalid}
                aria-describedby={
                  emailInvalid ? "login-email-error" : undefined
                }
              />
            </InputGroup>
            {emailInvalid ? (
              <FieldError id="login-email-error">
                {t("login.invalidEmail")}
              </FieldError>
            ) : null}
          </Field>

          <Field>
            <Label htmlFor="login-password">{t("fields.password")}</Label>
            <InputGroup className="h-11 rounded-lg">
              <InputGroupAddon>
                <Lock className="size-4" />
              </InputGroupAddon>
              <InputGroupInput
                id="login-password"
                name="password"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(event) => setPassword(event.currentTarget.value)}
                placeholder={t("login.passwordPlaceholder")}
                autoComplete="current-password"
                spellCheck={false}
                className="code-mono"
              />
              <InputGroupAddon align="inline-end">
                <InputGroupButton
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={
                    showPassword
                      ? t("actions.hidePassword")
                      : t("actions.showPassword")
                  }
                >
                  {showPassword ? (
                    <EyeOff className="size-4" />
                  ) : (
                    <Eye className="size-4" />
                  )}
                </InputGroupButton>
              </InputGroupAddon>
            </InputGroup>
          </Field>

          <Button
            className="h-11 w-full font-medium"
            disabled={
              loading ||
              !(localLogin ? isValidEmail(email) : email.trim()) ||
              !password
            }
            type="submit"
          >
            {loading ? t("login.signingIn") : t("login.submitWithEnter")}
          </Button>

          {registered ? (
            <p
              role="status"
              className="text-center text-sm text-muted-foreground"
            >
              {t("tokenRegister.success")}
            </p>
          ) : null}
          {error ? (
            <p className="text-center text-sm text-destructive">{error}</p>
          ) : null}

          {!localLogin ? (
            <p className="text-center text-sm text-muted-foreground">
              {t("login.newHere")}{" "}
              <button
                type="button"
                disabled={loading}
                onClick={() => setRegistering(true)}
                className="font-medium text-foreground underline-offset-4 hover:underline"
              >
                {t("login.signUp")}
              </button>
            </p>
          ) : null}

          {localLogin && oauthEnabled && oauthProviderLabel ? (
            <Button
              type="button"
              variant="outline"
              className="h-11 w-full gap-2"
              disabled={loading}
              onClick={() => void startOAuth()}
            >
              <Globe className="size-4" />
              {t("login.oauth", { provider: oauthProviderLabel })}
            </Button>
          ) : null}

          {localLogin && passwordResetEnabled ? (
            <Button
              type="button"
              variant="ghost"
              disabled={loading}
              onClick={() => navigate("forgot-password")}
            >
              {t("login.resetPassword")}
            </Button>
          ) : null}

          <PrivacyNotice message={t("login.privacyNotice")} />
        </FieldGroup>
      </form>
    </AuthShell>
  )
}
