import type { Metadata } from "next"
import { RegisterForm } from "@/components/auth/register-form"

export const metadata: Metadata = {
  title: "Create Account | AI Learning Platform",
  description: "Create an account to begin your personalized AI learning journey.",
}

export default function RegisterPage() {
  return <RegisterForm />
}
