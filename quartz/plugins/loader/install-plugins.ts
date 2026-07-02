#!/usr/bin/env node
import { installPlugins, parsePluginSource } from "./gitLoader.js"
import fs from "fs"
import path from "path"
import YAML from "yaml"

async function main() {
  const configPath = path.resolve(process.cwd(), "quartz.config.yaml")
  const fileContent = fs.readFileSync(configPath, "utf8")
  const quartzConfig = YAML.parse(fileContent)

  const plugins = quartzConfig.plugins || []
  const yamlExternalPlugins = plugins
    .map((p: any) => p?.source)
    .filter((source: string) => source && source.startsWith("github:"))

  const externalPlugins = quartzConfig.externalPlugins || yamlExternalPlugins

  if (externalPlugins.length === 0) {
    console.log("No external plugins to install.")
    return
  }

  console.log(`Installing ${externalPlugins.length} plugin(s) from Git...`)

  const specs = externalPlugins.map((source: string) => parsePluginSource(source))
  const installed = await installPlugins(specs, { verbose: true })

  if (installed.size === externalPlugins.length) {
    console.log("✓ All plugins installed successfully")
  } else {
    console.error(`✗ Only ${installed.size}/${externalPlugins.length} plugins installed`)
    process.exit(1)
  }
}

main().catch((err) => {
  console.error("Failed to install plugins:", err)
  process.exit(1)
})
