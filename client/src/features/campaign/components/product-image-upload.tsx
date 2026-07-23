import { type ChangeEvent } from "react"
import { ImagePlus, Upload, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Label } from "@/components/ui/label"

type ProductImageUploadProps = {
  files: File[]
  disabled: boolean
  onFilesChange: (files: File[]) => void
}

const maximumFiles = 4

export function ProductImageUpload({ files, disabled, onFilesChange }: ProductImageUploadProps) {
  const handleFilesChange = (event: ChangeEvent<HTMLInputElement>) => {
    const images = Array.from(event.target.files ?? []).filter((file) => file.type.startsWith("image/"))
    onFilesChange([...files, ...images].slice(0, maximumFiles))
    event.target.value = ""
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <Label htmlFor="products" className="text-sm font-medium text-[#393640]">Product images <span className="font-normal text-[#85828f]">optional</span></Label>
          <p className="mt-1 text-xs leading-5 text-[#85828f]">Ingested first, then used as visual anchors across scenes.</p>
        </div>
        <span className="text-xs text-[#85828f]">{files.length}/{maximumFiles}</span>
      </div>
      <label htmlFor="products" className="flex min-h-28 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-[#cfcac0] bg-white px-4 text-center transition-colors hover:border-[#6f5cc5] hover:bg-[#f8f6ff] focus-within:ring-2 focus-within:ring-[#6f5cc5]/30 has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60">
        <ImagePlus className="mb-2 size-5 text-[#6754bd]" />
        <span className="text-sm font-medium text-[#37343e]">Add images or browse</span>
        <span className="mt-1 text-xs text-[#85828f]">PNG, JPG, or WEBP. Up to 4 files.</span>
        <input id="products" className="sr-only" type="file" accept="image/png,image/jpeg,image/webp" multiple onChange={handleFilesChange} disabled={disabled || files.length >= maximumFiles} />
      </label>
      {files.length > 0 && <div className="flex flex-wrap gap-2">
        {files.map((file, index) => <Badge key={`${file.name}-${file.lastModified}-${index}`} variant="secondary" className="h-7 gap-1.5 bg-[#f0edf9] px-2.5 text-[#514d64]">
          <Upload className="size-3" /><span className="max-w-32 truncate">{file.name}</span>
          <button aria-label={`Remove ${file.name}`} className="ml-0.5 rounded-full hover:text-[#b15048]" type="button" onClick={() => onFilesChange(files.filter((_, fileIndex) => fileIndex !== index))}><X className="size-3" /></button>
        </Badge>)}
      </div>}
    </div>
  )
}
