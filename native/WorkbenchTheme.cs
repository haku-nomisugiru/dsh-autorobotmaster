using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace RoboMaster.Workbench
{
    internal static class WorkbenchTheme
    {
        internal static readonly Color Ink = Color.FromArgb(32, 32, 32);
        internal static readonly Color Muted = Color.FromArgb(105, 105, 105);
        internal static readonly Color Surface = Color.FromArgb(246, 246, 246);
        internal static readonly Color Accent = Color.FromArgb(48, 48, 48);
        internal static readonly Color Border = Color.FromArgb(218, 218, 218);
        internal static readonly Color Header = Color.FromArgb(30, 30, 30);
        internal static readonly Color HeaderMuted = Color.FromArgb(190, 190, 190);
        internal static readonly Color Selection = Color.FromArgb(228, 228, 228);

        // A 16-pixel RM monogram. Integer cell edges keep it crisp at each DPI.
        private static readonly string[] PixelRows = {
            "0000000000000000",
            "0111000000001110",
            "0100000000000010",
            "0000000000000000",
            "0011110001000100",
            "0010001001101100",
            "0010001001010100",
            "0011110001010100",
            "0010100001000100",
            "0010010001000100",
            "0010001001000100",
            "0000000000000000",
            "0100000000000010",
            "0111000000001110",
            "0000000000000000",
            "0000000000000000"

        };

        internal static void DrawPixelIcon(Graphics graphics, Rectangle bounds, bool light)
        {
            using (var brush = new SolidBrush(light ? Color.White : Ink))
                for (int y = 0; y < 16; y++)
                    for (int x = 0; x < 16; x++)
                        if (PixelRows[y][x] == '1')
                        {
                            int left = bounds.Left + x * bounds.Width / 16;
                            int top = bounds.Top + y * bounds.Height / 16;
                            int right = bounds.Left + (x + 1) * bounds.Width / 16;
                            int bottom = bounds.Top + (y + 1) * bounds.Height / 16;
                            graphics.FillRectangle(brush, left, top, right - left, bottom - top);
                        }
        }

        // SOLIDWORKS CreateTaskpaneView3 expects a 256-color image list and
        // treats RGB(192,192,192) as the transparent background.
        internal static Bitmap CreateTaskpaneIcon(int size)
        {
            using (var source = CreatePixelIcon(false, size))
            {
                var bitmap = new Bitmap(size, size, PixelFormat.Format8bppIndexed);
                var palette = bitmap.Palette;
                for (int i = 0; i < 256; i++) palette.Entries[i] = Color.FromArgb(i, i, i);
                bitmap.Palette = palette;
                var data = bitmap.LockBits(new Rectangle(0, 0, size, size), ImageLockMode.WriteOnly, PixelFormat.Format8bppIndexed);
                try
                {
                    var pixels = new byte[Math.Abs(data.Stride) * size];
                    for (int y = 0; y < size; y++)
                        for (int x = 0; x < size; x++)
                            pixels[y * Math.Abs(data.Stride) + x] = source.GetPixel(x, y).A == 0 ? (byte)192 : (byte)32;
                    Marshal.Copy(pixels, 0, data.Scan0, pixels.Length);
                }
                finally { bitmap.UnlockBits(data); }
                return bitmap;
            }
        }

        internal static Bitmap CreatePixelIcon(bool light, int size)
        {
            var bitmap = new Bitmap(size, size);
            using (var graphics = Graphics.FromImage(bitmap))
            {
                graphics.Clear(Color.Transparent);
                DrawPixelIcon(graphics, new Rectangle(0, 0, size, size), light);
            }
            return bitmap;
        }
    }

    internal sealed class PixelIconControl : Control
    {
        private bool light;
        public bool Light { get { return light; } set { light = value; Invalidate(); } }
        internal PixelIconControl()
        {
            SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint |
                ControlStyles.OptimizedDoubleBuffer | ControlStyles.SupportsTransparentBackColor, true);
            Size = new Size(20, 20);
            BackColor = Color.Transparent;
            TabStop = false;
            AccessibleName = "RoboMaster RM pixel icon";
        }
        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            WorkbenchTheme.DrawPixelIcon(e.Graphics, ClientRectangle, Light);
        }
    }

    // The system ProgressBar ignores ForeColor under Windows visual styles.
    // Keep its range/accessibility behavior and draw the track in the app palette.
    internal sealed class MonochromeProgressBar : ProgressBar
    {
        internal MonochromeProgressBar()
        {
            SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint |
                ControlStyles.OptimizedDoubleBuffer, true);
        }
        public new int Value { get { return base.Value; } set { base.Value = value; Invalidate(); } }
        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.Clear(WorkbenchTheme.Selection);
            double fraction = Maximum == Minimum ? 0 : (double)(Value - Minimum) / (Maximum - Minimum);
            int width = Math.Max(0, Math.Min(ClientSize.Width, (int)Math.Round(ClientSize.Width * fraction)));
            using (var brush = new SolidBrush(WorkbenchTheme.Accent))
                e.Graphics.FillRectangle(brush, 0, 0, width, ClientSize.Height);
        }
    }
}
