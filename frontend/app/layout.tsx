import "./globals.css";

export const metadata = {
  title: "Domko",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pl">
      <body className="h-screen w-screen overflow-hidden bg-neutral-900 text-white">
        {children}
      </body>
    </html>
  );
}
