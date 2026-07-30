import { Badge } from "@/components/ui/badge"

export function AppHero() {
  return (
    <section className="mb-8 grid gap-5 lg:grid-cols-[1fr_auto] lg:items-end">
      <div className="max-w-3xl">
        <Badge className="mb-4 bg-[#ede9ff] text-[#5d48c6] hover:bg-[#ede9ff]">AI campaign studio</Badge>
        <h1 className="max-w-2xl text-4xl font-semibold tracking-[-0.045em] text-[#242238] sm:text-5xl lg:text-6xl">
          Turn an idea into a reel you can prove.
        </h1>
        <p className="mt-4 max-w-xl text-base leading-7 text-[#666473] sm:text-lg">
          Build a vertical slideshow, review each slide as it self-corrects, then keep the full generation trail with the final export.
        </p>
      </div>
      <div className="hidden items-center gap-2 pb-1 text-sm text-[#6d6d7b] lg:flex">
        <span className="size-2 rounded-full bg-[#9c88ff]" />
        Slideshow mode
      </div>
    </section>
  )
}
