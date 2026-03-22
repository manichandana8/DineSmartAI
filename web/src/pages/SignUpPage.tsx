import { AuthLayout } from "@/components/AuthLayout";
import { SignUpForm } from "@/components/auth/SignUpForm";

const sideImg =
  "https://images.unsplash.com/photo-1550966871-3ed3cdb5ed0c?auto=format&fit=crop&w=1200&q=80";

export function SignUpPage() {
  return (
    <AuthLayout
      title="Create your account"
      subtitle="One profile—carried into every chat with the AI dining agent."
      imageSrc={sideImg}
      imageAlt=""
      footerLink={{ to: "/sign-in", label: "Sign in", hint: "Already have an account?" }}
    >
      <SignUpForm />
    </AuthLayout>
  );
}
