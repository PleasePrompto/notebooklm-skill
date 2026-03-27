#!/bin/bash

# Prisma Expert Diagnostic Tool
# Based on SKILL.md specifications

echo "🔍 === Environment Detection ==="
# Check Prisma version
echo "Checking Prisma version..."
npx prisma --version 2>/dev/null || echo "❌ Prisma not installed"

# Check database provider
echo "Checking Data Source Provider..."
grep "provider" prisma/schema.prisma 2>/dev/null | head -1 || echo "❌ No schema.prisma found"

# Check Prisma Client generation status
if [ -d "node_modules/.prisma/client" ]; then
    echo "✅ Prisma Client generated"
else
    echo "⚠️ Prisma Client not found in node_modules"
fi

echo -e "\n🩺 === Schema Diagnosis ==="
# Validate schema syntax and relations
echo "Validating schema..."
npx prisma validate

# Check for formatting issues
echo "Checking formatting..."
npx prisma format --check

echo -e "\n🔄 === Migration Status ==="
# Check for migration drift and history
if [ -d "prisma/migrations" ]; then
    echo "Recent migrations:"
    ls -la prisma/migrations/ | head -5
    echo "Checking migration status (requires DB connection)..."
    npx prisma migrate status

    echo -e "\n🔍 === Detailed Drift Analysis ==="
    echo "Generating SQL difference between Schema and Database..."
    npx prisma migrate diff --from-schema-datamodel prisma/schema.prisma --to-schema-datasource prisma/schema.prisma --script || echo "⚠️ Could not generate diff (check DB connection)"
else
    echo "ℹ️ No migrations folder found."
fi