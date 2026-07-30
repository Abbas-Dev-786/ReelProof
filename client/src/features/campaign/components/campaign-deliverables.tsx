import { useCallback, useEffect, useMemo, useState } from "react"
import { Download, Images, LoaderCircle, Play } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Carousel,
  type CarouselApi,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
} from "@/components/ui/carousel"
import { cn } from "@/lib/utils"
import type { Campaign } from "../types"

type CampaignDeliverablesProps = {
  campaign: Campaign
}

type DownloadState = "idle" | "images" | "video"

type CarouselSlide = {
  key: string
  assetUrl: string
  isTitle: boolean
  beat?: Campaign["beats"][number]
}

function fileStem(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48) || "campaign"
}

function extensionFromAsset(url: string, contentType: string | null, fallback: string) {
  const cleanUrl = url.split("?")[0]
  const urlExtension = cleanUrl.match(/\.([a-z0-9]{2,5})$/i)?.[1]
  if (urlExtension) return urlExtension.toLowerCase()

  const mimeExtension = contentType?.split(";")[0].split("/")[1]
  if (!mimeExtension) return fallback
  if (mimeExtension === "jpeg") return "jpg"
  if (mimeExtension === "quicktime") return "mov"
  return mimeExtension
}

async function downloadAsset(url: string, filenameWithoutExtension: string, fallbackExtension: string) {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`Download failed (${response.status})`)

  const blob = await response.blob()
  const extension = extensionFromAsset(url, blob.type, fallbackExtension)
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement("a")

  link.href = objectUrl
  link.download = `${filenameWithoutExtension}.${extension}`
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1_000)
}

export function CampaignDeliverables({ campaign }: CampaignDeliverablesProps) {
  const [api, setApi] = useState<CarouselApi>()
  const [activeSlide, setActiveSlide] = useState(0)
  const [downloadState, setDownloadState] = useState<DownloadState>("idle")
  const [downloadMessage, setDownloadMessage] = useState<string | null>(null)
  const campaignFileStem = useMemo(() => fileStem(campaign.topic), [campaign.topic])
  const slides = useMemo<CarouselSlide[]>(
    () => [
      ...(campaign.title_image_url
        ? [{ key: "title", assetUrl: campaign.title_image_url, isTitle: true }]
        : []),
      ...campaign.beats.map((beat) => ({
        key: `scene-${beat.index}`,
        assetUrl: beat.captioned_url ?? beat.image_url,
        isTitle: false,
        beat,
      })),
    ],
    [campaign.beats, campaign.title_image_url],
  )

  useEffect(() => {
    if (!api) return

    const updateActiveSlide = () => setActiveSlide(api.selectedScrollSnap())
    updateActiveSlide()
    api.on("select", updateActiveSlide)
    api.on("reInit", updateActiveSlide)

    return () => {
      api.off("select", updateActiveSlide)
      api.off("reInit", updateActiveSlide)
    }
  }, [api])

  const downloadImages = useCallback(async () => {
    setDownloadState("images")
    setDownloadMessage(null)

    try {
      if (campaign.title_image_url) {
        await downloadAsset(campaign.title_image_url, `${campaignFileStem}-title`, "png")
      }
      for (const beat of campaign.beats) {
        const assetUrl = beat.captioned_url ?? beat.image_url
        await downloadAsset(
          assetUrl,
          `${campaignFileStem}-scene-${String(beat.index + 1).padStart(2, "0")}`,
          "png",
        )
      }
      setDownloadMessage(`${slides.length} carousel images downloaded.`)
    } catch {
      setDownloadMessage("The images could not be downloaded. Please try again.")
    } finally {
      setDownloadState("idle")
    }
  }, [campaign.beats, campaign.title_image_url, campaignFileStem, slides.length])

  const downloadVideo = useCallback(async () => {
    if (!campaign.reel_url) return

    setDownloadState("video")
    setDownloadMessage(null)

    try {
      await downloadAsset(campaign.reel_url, `${campaignFileStem}-reel`, "mp4")
      setDownloadMessage("Final video downloaded.")
    } catch {
      setDownloadMessage("The final video could not be downloaded. Please try again.")
    } finally {
      setDownloadState("idle")
    }
  }, [campaign.reel_url, campaignFileStem])

  if (slides.length === 0) return null

  return (
    <section className="border-t border-[#e9e5de] pt-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-[#36333d]">
            {campaign.mode === "pov" ? "POV clips" : "Image carousel"}
          </h3>
          <p className="mt-1 text-xs text-[#817c88]">
            {activeSlide + 1} of {slides.length}
          </p>
        </div>
        <span className="text-xs text-[#817c88]">{slides.length} slides</span>
      </div>

      <Carousel className="mx-auto w-full max-w-[430px]" opts={{ loop: slides.length > 1 }} setApi={setApi}>
        <CarouselContent className="ms-0">
          {slides.map((slide) => {
            const hasPovClip = !slide.isTitle && campaign.mode === "pov" && Boolean(slide.beat?.video_url)

            return (
              <CarouselItem className="ps-0" key={slide.key}>
                <div className="relative aspect-[9/16] overflow-hidden rounded-lg bg-[#17171f]">
                  {hasPovClip ? (
                    <video
                      aria-label={`POV clip ${(slide.beat?.index ?? 0) + 1}`}
                      className="size-full object-contain"
                      controls
                      muted
                      playsInline
                      preload="metadata"
                      src={slide.beat?.video_url ?? undefined}
                    />
                  ) : (
                    <img
                      alt={slide.isTitle ? "Title slide" : `Carousel scene ${(slide.beat?.index ?? 0) + 1}`}
                      className="size-full object-contain"
                      src={slide.assetUrl}
                    />
                  )}

                  <div className="pointer-events-none absolute inset-x-0 top-0 flex items-center justify-between bg-gradient-to-b from-black/65 to-transparent px-3 pb-8 pt-3 text-white">
                    <span className="inline-flex items-center gap-1.5 text-xs font-medium">
                      {hasPovClip ? <Play className="size-3.5 fill-current" /> : <Images className="size-3.5" />}
                      {slide.isTitle ? "Title" : `Scene ${(slide.beat?.index ?? 0) + 1}`}
                    </span>
                    {slide.beat?.judge_score != null && <span className="text-[11px] text-white/80">Score {slide.beat.judge_score}</span>}
                  </div>
                </div>
              </CarouselItem>
            )
          })}
        </CarouselContent>

        {slides.length > 1 && (
          <>
            <CarouselPrevious className="start-3 z-10 border-white/25 bg-black/45 text-white shadow-sm hover:bg-black/65 hover:text-white" />
            <CarouselNext className="end-3 z-10 border-white/25 bg-black/45 text-white shadow-sm hover:bg-black/65 hover:text-white" />
          </>
        )}
      </Carousel>

      {slides.length > 1 && (
        <div aria-label="Choose carousel slide" className="mt-3 flex flex-wrap items-center justify-center gap-1.5">
          {slides.map((slide, index) => (
            <button
              aria-label={slide.isTitle ? "Go to title slide" : `Go to scene ${index + 1}`}
              aria-current={index === activeSlide ? "true" : undefined}
              className={cn(
                "h-1.5 rounded-full transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6f5cc5] focus-visible:ring-offset-2",
                index === activeSlide ? "w-6 bg-[#6856bf]" : "w-1.5 bg-[#cbc6d2] hover:bg-[#9d96aa]",
              )}
              key={slide.key}
              onClick={() => api?.scrollTo(index)}
              type="button"
            />
          ))}
        </div>
      )}

      <div className={cn("mt-4 grid gap-2", campaign.reel_url && "sm:grid-cols-2")}>
        <Button
          className="border-[#ded8ce]"
          disabled={downloadState !== "idle"}
          onClick={downloadImages}
          variant="outline"
        >
          {downloadState === "images" ? <LoaderCircle className="animate-spin" /> : <Images />}
          Download all images
        </Button>
        {campaign.reel_url && (
          <Button
            className="bg-[#7561d9] hover:bg-[#6550c5]"
            disabled={downloadState !== "idle"}
            onClick={downloadVideo}
          >
            {downloadState === "video" ? <LoaderCircle className="animate-spin" /> : <Download />}
            Download final MP4
          </Button>
        )}
      </div>

      <p
        aria-live="polite"
        className={cn(
          "mt-2 min-h-4 text-center text-xs",
          downloadMessage?.includes("could not") ? "text-[#b34f48]" : "text-[#76727c]",
        )}
      >
        {downloadMessage}
      </p>
    </section>
  )
}
