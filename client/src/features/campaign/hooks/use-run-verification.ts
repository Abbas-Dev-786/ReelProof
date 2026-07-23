import { useMutation } from "@tanstack/react-query"
import { verifyRun } from "../api"

export function useRunVerification() {
  return useMutation({ mutationFn: verifyRun })
}
