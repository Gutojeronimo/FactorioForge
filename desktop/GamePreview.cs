using System.Globalization;
using System.IO;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace ForgePlan;

sealed class GamePreview : FrameworkElement
{
    sealed record Layer(List<BitmapSource> Frames, double Width, double Height, Point Shift, bool Shadow, double Rotation);
    sealed record Graphic(string Name, string Kind, List<Layer> Layers, BitmapSource? Icon, double Width, double Height);
    sealed record Entity(Graphic Graphic, Point Position);
    sealed record Port(string Name, Point Position, bool Input, BitmapSource? Icon, string Note);
    readonly List<Entity> entities = new();
    readonly List<Port> ports = new();
    readonly List<(Point A, Point B)> wires = new();
    readonly DispatcherTimer timer = new() { Interval = TimeSpan.FromMilliseconds(85) };
    readonly ToolTip hover = new() { Placement = PlacementMode.MousePoint, StaysOpen = true };
    Rect bounds = new(0, 0, 20, 20);
    Point pan, lastPointer;
    Matrix transform;
    double zoom = 1;
    int frame;
    bool dragging;
    double flowAngle = -90;

    public GamePreview()
    {
        Focusable = true; ClipToBounds = true;
        timer.Tick += (_, _) => { if (entities.Count > 0 && IsVisible) { frame++; InvalidateVisual(); } };
        timer.Start(); SizeChanged += (_, _) => InvalidateVisual();
        MouseLeave += (_, _) => hover.IsOpen = false;
    }
    public void Stop() { timer.Stop(); hover.IsOpen = false; }
    public void Clear()
    {
        entities.Clear(); ports.Clear(); wires.Clear(); bounds = new Rect(0, 0, 20, 20); pan = new Point(); zoom = 1; InvalidateVisual();
    }
    public void ChangeZoom(double amount) { zoom = Math.Clamp(zoom + amount, .3, 4); InvalidateVisual(); }
    public void Fit() { zoom = 1; pan = new Point(); InvalidateVisual(); }
    public void SetResult(JsonNode data)
    {
        entities.Clear(); ports.Clear(); wires.Clear();
        flowAngle = -90 + J.N(data["layout"]?["config"], "rotation") * 90;
        var graphics = new Dictionary<string, Graphic>();
        if (data["graphics"] is JsonObject descriptors)
        {
            foreach (var pair in descriptors)
            {
                var layers = new List<Layer>();
                foreach (var layer in J.A(pair.Value, "layers"))
                {
                    var frames = new List<BitmapSource>();
                    foreach (var crop in J.A(layer, "frames"))
                    {
                        var sheet = Art.Load(J.S(crop, "path")); if (sheet == null) continue;
                        var rect = new Int32Rect((int)J.N(crop, "x"), (int)J.N(crop, "y"), (int)J.N(crop, "w"), (int)J.N(crop, "h"));
                        if (rect.Width <= 0 || rect.Height <= 0 || rect.X + rect.Width > sheet.PixelWidth || rect.Y + rect.Height > sheet.PixelHeight) continue;
                        var bitmap = new CroppedBitmap(sheet, rect); bitmap.Freeze(); frames.Add(bitmap);
                    }
                    if (frames.Count == 0) continue;
                    var shift = J.A(layer, "shift");
                    layers.Add(new Layer(frames, J.N(layer, "width", 1), J.N(layer, "height", 1), new Point(shift.Count > 0 ? shift[0]!.GetValue<double>() : 0, shift.Count > 1 ? shift[1]!.GetValue<double>() : 0), J.B(layer, "shadow"), J.N(layer, "rotation")));
                }
                var footprint = J.A(pair.Value, "footprint");
                graphics[pair.Key] = new Graphic(J.S(pair.Value, "name"), J.S(pair.Value, "type"), layers, Art.LoadIcon(J.S(pair.Value, "icon")), footprint.Count > 0 ? footprint[0]!.GetValue<double>() : 1, footprint.Count > 1 ? footprint[1]!.GetValue<double>() : 1);
            }
        }
        foreach (var entity in J.A(data, "entities"))
        {
            var name = J.S(entity, "name"); var key = name + "|" + (int)J.N(entity, "direction") + "|" + J.S(entity, "type");
            if (graphics.TryGetValue(key, out var graphic)) entities.Add(new Entity(graphic, new Point(J.N(entity?["position"], "x"), J.N(entity?["position"], "y"))));
        }
        foreach (var port in J.A(data, "ports"))
        {
            var name = J.S(port, "name"); var input = J.S(port, "kind") == "input";
            ports.Add(new Port(name, new Point(J.N(port, "x"), J.N(port, "y")), input, Art.LoadIcon(J.S(data["icons"], name)), J.S(port, "note")));
        }
        var byId = J.A(data, "entities").ToDictionary(e => (int)J.N(e, "entity_number"));
        foreach (var wire in J.A(data["layout"], "wires").OfType<JsonArray>())
        {
            if (wire.Count < 4 || !byId.TryGetValue(wire[0]!.GetValue<int>(), out var a) || !byId.TryGetValue(wire[2]!.GetValue<int>(), out var b)) continue;
            wires.Add((new Point(J.N(a?["position"], "x"), J.N(a?["position"], "y") - 1.5), new Point(J.N(b?["position"], "x"), J.N(b?["position"], "y") - 1.5)));
        }
        var union = Rect.Empty;
        foreach (var entity in entities)
        {
            union.Union(new Rect(entity.Position.X - entity.Graphic.Width / 2, entity.Position.Y - entity.Graphic.Height / 2, entity.Graphic.Width, entity.Graphic.Height));
            foreach (var layer in entity.Graphic.Layers)
            {
                var extent = Math.Max(layer.Width, layer.Height);
                union.Union(new Rect(entity.Position.X + layer.Shift.X - extent / 2, entity.Position.Y + layer.Shift.Y - extent / 2, extent, extent));
            }
        }
        foreach (var port in ports) union.Union(new Rect(port.Position.X - .65, port.Position.Y - .65, 1.3, 1.3));
        if (!union.IsEmpty) { union.Inflate(1.4, 1.4); bounds = union; }
        Fit();
    }
    protected override void OnRender(DrawingContext dc)
    {
        base.OnRender(dc); dc.DrawRectangle(UI.Brush("#262C25"), null, new Rect(RenderSize));
        if (ActualWidth < 1 || ActualHeight < 1) return;
        if (entities.Count == 0)
        {
            var message = new FormattedText("Selecione uma receita para visualizar a fábrica", CultureInfo.CurrentCulture, FlowDirection.LeftToRight, new Typeface("Segoe UI"), 14, UI.Muted, VisualTreeHelper.GetDpi(this).PixelsPerDip);
            dc.DrawText(message, new Point(Math.Max(14, (ActualWidth - message.Width) / 2), ActualHeight / 2)); return;
        }
        var scale = Math.Min((ActualWidth - 40) / bounds.Width, (ActualHeight - 40) / bounds.Height) * zoom;
        transform = new Matrix(scale, 0, 0, scale, ActualWidth / 2 - (bounds.X + bounds.Width / 2) * scale + pan.X, ActualHeight / 2 - (bounds.Y + bounds.Height / 2) * scale + pan.Y);
        dc.PushTransform(new MatrixTransform(transform));
        var grid = new Pen(UI.Brush("#354031"), .014);
        for (var x = Math.Floor(bounds.Left - 20); x < bounds.Right + 20; x++) dc.DrawLine(grid, new Point(x, bounds.Top - 20), new Point(x, bounds.Bottom + 20));
        for (var y = Math.Floor(bounds.Top - 20); y < bounds.Bottom + 20; y++) dc.DrawLine(grid, new Point(bounds.Left - 20, y), new Point(bounds.Right + 20, y));
        foreach (var entity in entities) DrawLayers(dc, entity, true);
        foreach (var entity in entities.OrderBy(e => e.Graphic.Kind == "transport-belt" ? 0 : 1).ThenBy(e => e.Position.Y))
        {
            if (entity.Graphic.Layers.Count > 0) DrawLayers(dc, entity, false);
            else
            {
                var area = new Rect(entity.Position.X - entity.Graphic.Width / 2, entity.Position.Y - entity.Graphic.Height / 2, entity.Graphic.Width, entity.Graphic.Height);
                dc.DrawRoundedRectangle(UI.Brush("#334430"), new Pen(UI.Lime, .035), area, .08, .08);
                if (entity.Graphic.Icon != null) dc.DrawImage(entity.Graphic.Icon, area);
            }
        }
        foreach (var wire in wires)
        {
            var geometry = new StreamGeometry();
            using (var context = geometry.Open()) { context.BeginFigure(wire.A, false, false); context.QuadraticBezierTo(new Point((wire.A.X + wire.B.X) / 2, (wire.A.Y + wire.B.Y) / 2 + .35), wire.B, true, false); }
            dc.DrawGeometry(null, new Pen(UI.Brush("#A88543"), .025), geometry);
        }
        foreach (var port in ports)
        {
            var area = new Rect(port.Position.X - .37, port.Position.Y - .37, .74, .74);
            dc.DrawRoundedRectangle(UI.Brush("#152218"), new Pen(UI.Brush("#809D51"), .025), area, .09, .09);
            if (port.Icon != null) dc.DrawImage(port.Icon, new Rect(area.X + .055, area.Y + .055, .63, .63));
            dc.PushTransform(new RotateTransform(flowAngle, port.Position.X, port.Position.Y));
            var y = port.Position.Y + (port.Input ? .65 : -.65);
            dc.DrawLine(new Pen(UI.Lime, .055), new Point(port.Position.X, y - .15), new Point(port.Position.X, y + .15));
            dc.DrawLine(new Pen(UI.Lime, .055), new Point(port.Position.X - .1, y + .04), new Point(port.Position.X, y + .15));
            dc.DrawLine(new Pen(UI.Lime, .055), new Point(port.Position.X + .1, y + .04), new Point(port.Position.X, y + .15));
            dc.Pop();
        }
        dc.Pop();
    }
    void DrawLayers(DrawingContext dc, Entity entity, bool shadow)
    {
        foreach (var layer in entity.Graphic.Layers.Where(l => l.Shadow == shadow))
        {
            var bitmap = layer.Frames[frame % layer.Frames.Count];
            if (layer.Rotation != 0) dc.PushTransform(new RotateTransform(layer.Rotation, entity.Position.X, entity.Position.Y));
            dc.DrawImage(bitmap, new Rect(entity.Position.X + layer.Shift.X - layer.Width / 2, entity.Position.Y + layer.Shift.Y - layer.Height / 2, layer.Width, layer.Height));
            if (layer.Rotation != 0) dc.Pop();
        }
    }
    protected override void OnMouseWheel(MouseWheelEventArgs e) { ChangeZoom(e.Delta > 0 ? .2 : -.2); e.Handled = true; }
    protected override void OnMouseLeftButtonDown(MouseButtonEventArgs e) { dragging = true; lastPointer = e.GetPosition(this); CaptureMouse(); hover.IsOpen = false; Cursor = Cursors.SizeAll; }
    protected override void OnMouseLeftButtonUp(MouseButtonEventArgs e) { dragging = false; ReleaseMouseCapture(); Cursor = Cursors.Arrow; }
    protected override void OnMouseMove(MouseEventArgs e)
    {
        var pointer = e.GetPosition(this);
        if (dragging) { pan = new Point(pan.X + pointer.X - lastPointer.X, pan.Y + pointer.Y - lastPointer.Y); lastPointer = pointer; InvalidateVisual(); return; }
        if (!transform.HasInverse) return;
        var inverse = transform; inverse.Invert(); var world = inverse.Transform(pointer);
        var port = ports.LastOrDefault(p => Math.Abs(p.Position.X - world.X) < .5 && Math.Abs(p.Position.Y - world.Y) < .5);
        var entity = entities.OrderBy(e => e.Position.Y).LastOrDefault(e => Math.Abs(e.Position.X - world.X) <= e.Graphic.Width / 2 && Math.Abs(e.Position.Y - world.Y) <= e.Graphic.Height / 2);
        var name = port?.Name ?? entity?.Graphic.Name;
        if (name == null) { hover.IsOpen = false; return; }
        hover.PlacementTarget = this; hover.Content = J.Label(name) + "\n" + name + (port != null ? "\n" + port.Note : ""); hover.IsOpen = true;
    }
    public void SavePng(string path)
    {
        var bitmap = new RenderTargetBitmap((int)ActualWidth * 2, (int)ActualHeight * 2, 192, 192, PixelFormats.Pbgra32); bitmap.Render(this);
        var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap)); using var file = File.Create(path); encoder.Save(file);
    }
}
