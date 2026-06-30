const getStartupStart = () => {
  if (!globalThis.__APP_STARTUP_PERF_START__) {
    globalThis.__APP_STARTUP_PERF_START__ = performance.now()
  }
  return globalThis.__APP_STARTUP_PERF_START__
}

const formatFields = (fields = {}) => Object.fromEntries(
  Object.entries(fields).filter(([, value]) => value !== undefined)
)

export const startupPerfMark = (stage, fields = {}) => {
  const totalMs = performance.now() - getStartupStart()
  console.debug('[StartupPerf][frontend]', {
    stage,
    total_ms: Number(totalMs.toFixed(2)),
    ...formatFields(fields),
  })
  return performance.now()
}

export const startupPerfMeasure = async (stage, runner, fields = {}) => {
  const startedAt = performance.now()
  try {
    return await runner()
  } finally {
    const stepMs = performance.now() - startedAt
    startupPerfMark(stage, {
      step_ms: Number(stepMs.toFixed(2)),
      ...fields,
    })
  }
}
