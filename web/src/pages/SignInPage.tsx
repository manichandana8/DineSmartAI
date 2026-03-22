import { AuthLayout } from "@/components/AuthLayout";
import { SignInForm } from "@/components/auth/SignInForm";

const sideImg =
  "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=1200&q=80";

export function SignInPage() {
  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Sign in to sync your taste profile with the DineSmartAI agent."
      imageSrc={sideImg}
      imageAlt=""
      footerLink={{ to: "/sign-up", label: "Create one", hint: "New to DineSmartAI?" }}
    >
      <SignInForm />
    </AuthLayout>
  );
}
