import type { Metadata } from "next"
import { LoginForm } from "@/components/auth/login-form"

export const metadata: Metadata = {
  title: "Sign In | AI Learning Platform",
  description: "Sign in to your personalized AI learning workspace.",
}

export default function LoginPage() {
  return <LoginForm />
}
