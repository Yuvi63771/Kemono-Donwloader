<h1>Kemono Downloader - Comprehensive Feature Guide</h1>
<p>This guide provides a detailed overview of all user interface elements, input fields, buttons, popups, and functionalities available in the application.</p>
<hr>
<h2>1. Core Concepts &amp; Supported Sites</h2>
<h3>URL Input (🔗)</h3>
<p>This is the primary input field where you specify the content you want to download.</p>
<p><strong>Supported URL Types:</strong></p>
<ul>
  <li><strong>Creator URL</strong>: A link to a creator's main page. Downloads all posts from that creator.</li>
  <li><strong>Post URL</strong>: A direct link to a specific post. Downloads only that single post.</li>
  <li><strong>Batch Command</strong>: Special keywords to trigger bulk downloading from a text file (see Batch Downloading section).</li>
</ul>
<p><strong>Supported Websites:</strong></p>
<ul>
  <li>Kemono (<code>kemono.su</code>, <code>kemono.party</code>, etc.)</li>
  <li>Coomer (<code>coomer.su</code>, <code>coomer.party</code>, etc.)</li>
  <li>Discord (via Kemono/Coomer API)</li>
  <li>Bunkr</li>
  <li>Erome</li>
  <li>Saint2.su</li>
  <li>nhentai</li>
</ul>
<hr>
<h2>2. Main Download Controls &amp; Inputs</h2>
<h3>Download Location (📁)</h3>
<p>This input defines the main folder where your files will be saved.</p>
<ul>
  <li><strong>Browse Button</strong>: Opens a system dialog to choose a folder.</li>
  <li><strong>Directory Creation</strong>: If the folder doesn't exist, the app will ask for confirmation to create it.</li>
</ul>
<h3>Filter by Character(s) &amp; Scope</h3>
<p>Used to download content for specific characters or series and organize them into subfolders.</p>
<ul>
  <li><strong>Input Field</strong>: Enter comma-separated names (e.g., <code>Tifa, Aerith</code>). Group aliases using parentheses for folder naming (e.g., <code>(Cloud, Zack)</code>).</li>
  <li><strong>Scope Button</strong>: Cycles through where to look for name matches:
    <ul>
      <li><strong>Filter: Title</strong>: Matches names in the post title.</li>
      <li><strong>Filter: Files</strong>: Matches names in the filenames.</li>
      <li><strong>Filter: Both</strong>: Checks the title first, then filenames.</li>
      <li><strong>Filter: Comments</strong>: Checks filenames first, then post comments.</li>
    </ul>
  </li>
</ul>
<h3>Skip with Words &amp; Scope</h3>
<p>Prevents downloading content based on keywords or file size.</p>
<ul>
  <li><strong>Input Field</strong>: Enter comma-separated keywords (e.g., <code>WIP, sketch, preview</code>).</li>
  <li><strong>Skip by Size</strong>: Enter a number in square brackets to skip any file <strong>smaller than</strong> that size in MB. For example, <code>WIP, [200]</code> skips files with "WIP" in the name AND any file smaller than 200 MB.</li>
  <li><strong>Scope Button</strong>: Cycles through where to apply keyword filters:
    <ul>
      <li><strong>Scope: Posts</strong>: Skips the entire post if the title matches.</li>
      <li><strong>Scope: Files</strong>: Skips individual files if the filename matches.</li>
      <li><strong>Scope: Both</strong>: Checks the post title first, then individual files.</li>
    </ul>
  </li>
</ul>
<h3>Remove Words from Name (✂️)</h3>
<p>Enter comma-separated words to remove from final filenames (e.g., <code>patreon, [HD]</code>). This helps clean up file naming.</p>
<hr>
<h2>3. Primary Download Modes (Filter File Section)</h2>
<p>This section uses radio buttons to set the main download mode. Only one can be active at a time.</p>
<ul>
  <li><strong>All</strong>: Default mode. Downloads every file and attachment.</li>
  <li><strong>Images/GIFs</strong>: Downloads only common image formats.</li>
  <li><strong>Videos</strong>: Downloads only common video formats.</li>
  <li><strong>Only Archives</strong>: Downloads only <code>.zip</code>, <code>.rar</code>, etc.</li>
  <li><strong>Only Audio</strong>: Downloads only common audio formats.</li>
  <li><strong>Only Links</strong>: Extracts external hyperlinks (e.g., Mega, Google Drive) from post descriptions instead of downloading files. <strong>This mode unlocks special features</strong> (see section 6).</li>
  <li><strong>More</strong>: Opens a dialog to download text-based content.
    <ul>
      <li><strong>Scope</strong>: Choose to extract text from the post description or comments.</li>
      <li><strong>Export Format</strong>: Save as PDF, DOCX, or TXT.</li>
      <li><strong>Single PDF</strong>: Compile all text from the session into one consolidated PDF file.</li>
    </ul>
  </li>
</ul>
<hr>
<h2>4. Advanced Features &amp; Toggles (Checkboxes)</h2>
<h3>Folder Organization</h3>
<ul>
  <li><strong>Separate folders by Known.txt</strong>: Automatically organizes downloads into subfolders based on name matches from your <code>Known.txt</code> list or the "Filter by Character(s)" input.</li>
  <li><strong>Subfolder per post</strong>: Creates a unique folder for each post, named after the post's title. This prevents files from different posts from mixing.</li>
  <li><strong>Date prefix</strong>: (Only available with "Subfolder per post") Prepends the post date to the folder name (e.g., <code>2025-08-03 My Post Title</code>) for chronological sorting.</li>
</ul>
<h3>Special Modes</h3>
<ul>
  <li><strong>⭐ Favorite Mode</strong>: Switches the UI to download from your personal favorites list instead of using the URL input.</li>
  <li><strong>Manga/Comic mode</strong>: Sorts a creator's posts from oldest to newest before downloading, ensuring correct page order. A scope button appears to control the filename style (e.g., using post title, date, or a global number).</li>
</ul>
<h3>File Handling</h3>
<ul>
  <li><strong>Skip Archives</strong>: Ignores <code>.zip</code> and <code>.rar</code> files during downloads.</li>
  <li><strong>Download Thumbnail Only</strong>: Saves only the small preview images instead of full-resolution files.</li>
  <li><strong>Scan Content for Images</strong>: Parses post HTML to find embedded images that may not be listed in the API data.</li>
  <li><strong>Compress to WebP</strong>: Converts large images (over 1.5 MB) to the space-saving WebP format.</li>
  <li><strong>Keep Duplicates</strong>: Opens a dialog to control how duplicate files are handled (skip by default, keep all, or keep a specific number of copies).</li>
</ul>
<h3>General Functionality</h3>
<ul>
  <li><strong>Use cookie</strong>: Enables login-based access. You can paste a cookie string or browse for a <code>cookies.txt</code> file.</li>
  <li><strong>Use Multithreading</strong>: Enables parallel processing of posts for faster downloads. You can set the number of concurrent worker threads.</li>
  <li><strong>Show external links in log</strong>: Opens a secondary log panel that displays external links found in post descriptions.</li>
</ul>
<hr>
<h2>5. Specialized Downloaders &amp; Batch Mode</h2>
<h3>Discord Features</h3>
<ul>
  <li>When a Discord URL is entered, a <strong>Scope</strong> button appears.
    <ul>
      <li><strong>Scope: Files</strong>: Downloads all files from the channel/server.</li>
      <li><strong>Scope: Messages</strong>: Saves the entire message history of the channel/server as a formatted PDF.</li>
    </ul>
  </li>
  <li>A <strong>"Save as PDF"</strong> button also appears as a shortcut for the message saving feature.</li>
</ul>
<h3>Batch Downloading (<code>nhentai</code> &amp; <code>saint2.su</code>)</h3>
<p>This feature allows you to download hundreds of galleries or videos from a simple text file.</p>
<ol>
  <li>In the <code>appdata</code> folder, create <code>nhentai.txt</code> or <code>saint2.su.txt</code>.</li>
  <li>Add one full URL per line to the corresponding file.</li>
  <li>In the app's URL input, type either <code>nhentai.net</code> or <code>saint2.su</code> and click "Start Download".</li>
  <li>The app will read the file and process every URL in the queue.</li>
</ol>
<hr>
<h2>6. "Only Links" Mode: Extraction &amp; Direct Download</h2>
<p>When you select the <strong>"Only Links"</strong> radio button, the application's behavior changes significantly.</p>
<ul>
  <li><strong>Link Extraction</strong>: Instead of downloading files, the main log panel will fill with all external links found (Mega, Google Drive, Dropbox, etc.).</li>
  <li><strong>Export Links</strong>: An "Export Links" button appears, allowing you to save the full list of extracted URLs to a <code>.txt</code> file.</li>
  <li><strong>Direct Cloud Download</strong>: A <strong>"Download"</strong> button appears next to the export button.
    <ul>
      <li>Clicking this opens a new dialog listing all supported cloud links (Mega, G-Drive, Dropbox).</li>
      <li>You can select which files you want to download from this list.</li>
      <li>The application will then download the selected files directly from the cloud service to your chosen download location.</li>
    </ul>
  </li>
</ul>
<hr>
<h2>7. Session &amp; Process Management</h2>
<h3>Main Action Buttons</h3>
<ul>
  <li><strong>Start Download</strong>: Begins the download process. This button's text changes contextually (e.g., "Extract Links", "Check for Updates").</li>
  <li><strong>Pause / Resume</strong>: Pauses or resumes the ongoing download. When paused, you can safely change some settings.</li>
  <li><strong>Cancel &amp; Reset UI</strong>: Stops the current download and performs a soft reset of the UI, preserving your URL and download location.</li>
</ul>
<h3>Restore Interrupted Download</h3>
<p>If the application is closed unexpectedly during a download, it will save its progress.</p>
<ul>
  <li>On the next launch, the UI will be pre-filled with the settings from the interrupted session.</li>
  <li>The <strong>Pause</strong> button will change to <strong>"🔄 Restore Download"</strong>. Clicking it will resume the download exactly where it left off, skipping already processed posts.</li>
  <li>The <strong>Cancel</strong> button will change to <strong>"🗑️ Discard Session"</strong>, allowing you to clear the saved state and start fresh.</li>
</ul>
<h3>Other UI Controls</h3>
<ul>
  <li><strong>Error Button</strong>: Shows a count of failed files. Clicking it opens a dialog where you can view, export, or retry the failed downloads.</li>
  <li><strong>History Button</strong>: Shows a log of recently downloaded files and processed posts.</li>
  <li><strong>Settings Button</strong>: Opens the settings dialog where you can change the theme, language, and <strong>check for application updates</strong>.</li>
  <li><strong>Support Button</strong>: Opens a dialog with links to the project's source code and developer support pages.</li>
</ul>
