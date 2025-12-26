#!/usr/bin/env node

/**
 * Sync Local Folders to Google Drive for NotebookLM
 * 將本地資料夾同步到 Google Drive，供 NotebookLM 使用
 *
 * Usage:
 *   node sync-to-drive.js --local ~/PKM/Argus --drive "NotebookLM-Sources/Argus"
 *   node sync-to-drive.js --config ~/.claude/skills/notebooklm/sync-config.json
 */

const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');

// 憑證路徑 (使用現有的 OAuth)
const CREDENTIALS_PATH = path.join(
  process.env.HOME,
  'Dropbox/PKM-Vault/.ai-butler-system/credentials/google-oauth-credentials.json'
);

const TOKEN_PATH = path.join(
  process.env.HOME,
  'Dropbox/PKM-Vault/.ai-butler-system/credentials/google-oauth-token.json'
);

// 支援的檔案類型
const SUPPORTED_EXTENSIONS = ['.md', '.pdf', '.txt', '.docx'];

async function getAuthClient() {
  const credentials = JSON.parse(fs.readFileSync(CREDENTIALS_PATH, 'utf8'));
  const { client_secret, client_id, redirect_uris } = credentials.installed;

  const oAuth2Client = new google.auth.OAuth2(
    client_id,
    client_secret,
    redirect_uris[0]
  );

  const token = JSON.parse(fs.readFileSync(TOKEN_PATH, 'utf8'));
  oAuth2Client.setCredentials(token);

  return oAuth2Client;
}

async function findOrCreateFolder(drive, folderPath, parentId = 'root') {
  const folders = folderPath.split('/').filter(f => f);
  let currentParentId = parentId;

  for (const folderName of folders) {
    // 搜尋現有資料夾
    const response = await drive.files.list({
      q: `name='${folderName}' and '${currentParentId}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false`,
      fields: 'files(id, name)',
      spaces: 'drive'
    });

    if (response.data.files.length > 0) {
      currentParentId = response.data.files[0].id;
    } else {
      // 建立資料夾
      const folder = await drive.files.create({
        resource: {
          name: folderName,
          mimeType: 'application/vnd.google-apps.folder',
          parents: [currentParentId]
        },
        fields: 'id'
      });
      currentParentId = folder.data.id;
      console.log(`📁 Created folder: ${folderName}`);
    }
  }

  return currentParentId;
}

async function uploadFile(drive, localPath, folderId, existingFiles) {
  const fileName = path.basename(localPath);
  const ext = path.extname(localPath).toLowerCase();

  // 檢查是否已存在
  const existing = existingFiles.find(f => f.name === fileName || f.name === fileName.replace('.md', ''));

  let mimeType;
  let convertToGoogleDocs = false;

  switch (ext) {
    case '.md':
    case '.txt':
      mimeType = 'text/plain';
      convertToGoogleDocs = true;
      break;
    case '.pdf':
      mimeType = 'application/pdf';
      break;
    case '.docx':
      mimeType = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
      convertToGoogleDocs = true;
      break;
    default:
      console.log(`  ⏭️  Skipping unsupported file: ${fileName}`);
      return null;
  }

  const fileMetadata = {
    name: convertToGoogleDocs ? fileName.replace(ext, '') : fileName,
    parents: existing ? undefined : [folderId]
  };

  const media = {
    mimeType: mimeType,
    body: fs.createReadStream(localPath)
  };

  try {
    if (existing) {
      // 更新現有檔案
      const response = await drive.files.update({
        fileId: existing.id,
        media: media,
        fields: 'id, name, webViewLink'
      });
      console.log(`  🔄 Updated: ${fileName}`);
      return response.data;
    } else {
      // 建立新檔案
      const resource = {
        ...fileMetadata,
        ...(convertToGoogleDocs && { mimeType: 'application/vnd.google-apps.document' })
      };

      const response = await drive.files.create({
        resource: resource,
        media: media,
        fields: 'id, name, webViewLink'
      });
      console.log(`  ✅ Uploaded: ${fileName}`);
      return response.data;
    }
  } catch (error) {
    console.error(`  ❌ Error uploading ${fileName}:`, error.message);
    return null;
  }
}

async function syncFolder(drive, localPath, driveFolderPath) {
  console.log(`\n📂 Syncing: ${localPath} → ${driveFolderPath}`);

  // 確保資料夾存在
  const folderId = await findOrCreateFolder(drive, driveFolderPath);
  console.log(`  📁 Drive folder ID: ${folderId}`);

  // 取得 Drive 上的現有檔案
  const existingResponse = await drive.files.list({
    q: `'${folderId}' in parents and trashed=false`,
    fields: 'files(id, name, modifiedTime)',
    spaces: 'drive'
  });
  const existingFiles = existingResponse.data.files;

  // 讀取本地檔案
  const localFiles = fs.readdirSync(localPath).filter(f => {
    const ext = path.extname(f).toLowerCase();
    return SUPPORTED_EXTENSIONS.includes(ext);
  });

  console.log(`  📄 Found ${localFiles.length} files to sync`);

  let uploaded = 0;
  let updated = 0;
  let skipped = 0;

  for (const file of localFiles) {
    const filePath = path.join(localPath, file);
    const stat = fs.statSync(filePath);

    if (!stat.isFile()) continue;

    const result = await uploadFile(drive, filePath, folderId, existingFiles);
    if (result) {
      if (existingFiles.find(f => f.name === file || f.name === file.replace(path.extname(file), ''))) {
        updated++;
      } else {
        uploaded++;
      }
    } else {
      skipped++;
    }
  }

  console.log(`  📊 Summary: ${uploaded} uploaded, ${updated} updated, ${skipped} skipped`);
  return { folderId, uploaded, updated, skipped };
}

async function main() {
  const args = process.argv.slice(2);

  // 解析參數
  let localPath, drivePath, configPath;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--local' && args[i + 1]) {
      localPath = args[++i].replace('~', process.env.HOME);
    } else if (args[i] === '--drive' && args[i + 1]) {
      drivePath = args[++i];
    } else if (args[i] === '--config' && args[i + 1]) {
      configPath = args[++i].replace('~', process.env.HOME);
    }
  }

  // 初始化 Drive API
  const auth = await getAuthClient();
  const drive = google.drive({ version: 'v3', auth });

  if (configPath) {
    // 使用設定檔同步多個資料夾
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    console.log(`🔧 Using config: ${configPath}`);

    for (const mapping of config.sync_mappings) {
      if (!mapping.enabled) continue;

      const local = mapping.local_path.replace('~', process.env.HOME);
      if (!fs.existsSync(local)) {
        console.log(`⚠️  Local path not found: ${local}`);
        continue;
      }

      await syncFolder(drive, local, mapping.drive_folder);
    }
  } else if (localPath && drivePath) {
    // 單一資料夾同步
    if (!fs.existsSync(localPath)) {
      console.error(`❌ Local path not found: ${localPath}`);
      process.exit(1);
    }

    await syncFolder(drive, localPath, drivePath);
  } else {
    console.log(`
NotebookLM Drive Sync Tool
==========================

Usage:
  node sync-to-drive.js --local <path> --drive <drive-folder>
  node sync-to-drive.js --config <config.json>

Examples:
  node sync-to-drive.js --local ~/PKM/Argus --drive "NotebookLM-Sources/Argus"
  node sync-to-drive.js --config ~/.claude/skills/notebooklm/sync-config.json

Supported file types: ${SUPPORTED_EXTENSIONS.join(', ')}
    `);
  }

  console.log('\n✅ Sync complete!');
}

main().catch(console.error);
