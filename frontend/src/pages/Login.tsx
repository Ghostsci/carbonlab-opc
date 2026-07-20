import { useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import { Link, useNavigate } from "react-router-dom";

export default function Login() {
  const { login, isLoading } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    
    try {
      await login(email, password);
      navigate("/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="w-full max-w-md bg-stone-900 border border-stone-800 rounded-xl p-8">
        <h2 className="text-2xl font-bold text-stone-200 mb-6 text-center">登录 CarbonLab</h2>
        {error && (
          <div className="mb-4 p-3 bg-red-950/50 border border-red-800 rounded-lg text-red-400 text-sm">
            {error}
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-stone-400 text-sm mb-1">邮箱</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-4 py-2 bg-stone-800 border border-stone-700 rounded-lg text-stone-200 focus:outline-none focus:border-emerald-600"
              required
              autoFocus
            />
          </div>
          <div>
            <label className="block text-stone-400 text-sm mb-1">密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-2 bg-stone-800 border border-stone-700 rounded-lg text-stone-200 focus:outline-none focus:border-emerald-600"
              required
              minLength={6}
            />
          </div>
          <button
            type="submit"
            disabled={isLoading || submitting}
            className="w-full py-2 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white rounded-lg transition-colors font-medium"
          >
            {isLoading || submitting ? "登录中..." : "登录"}
          </button>
        </form>
        <p className="mt-4 text-center text-stone-500 text-sm">
          还没有账号？{" "}
          <Link to="/register" className="text-emerald-400 hover:text-emerald-300">
            注册
          </Link>
          {" · "}
          <Link to="/welcome" className="text-stone-400 hover:text-stone-300">
            了解 CarbonLab
          </Link>
        </p>
      </div>
    </div>
  );
}
