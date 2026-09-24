/// makernotes.rs — Parser de MakerNotes EXIF para extraer el punto de enfoque
/// activo usado por la cámara durante la captura.
///
/// Soporta los fabricantes con mayor cuota de mercado en fotografía de eventos:
///   - Nikon: IFD privado en MakerNotes, tag 0x0022 (AFInfo2) o 0x00B7 (AFInfo3)
///   - Sony:  IFD privado, tag 0x0094 (AFPoints) o 0x2010 (AFInfo)
///   - Canon: tag 0x0026 (AFInfo2) en el bloque Canon MakerNote
///
/// El resultado es un punto normalizado (0.0–1.0, 0.0–1.0) relativo al encuadre,
/// más un flag `is_focused` que indica si ese punto realmente bloqueó foco.

/// Punto de enfoque extraído.
#[derive(Debug, Clone)]
pub struct FocusPoint {
    /// Posición horizontal normalizada (0.0 = izquierda, 1.0 = derecha).
    pub x: f32,
    /// Posición vertical normalizada (0.0 = arriba, 1.0 = abajo).
    pub y: f32,
    /// True si la cámara confirmó foco en este punto.
    pub is_focused: bool,
}

/// Lee u16 little-endian desde un slice en `pos`.
fn le_u16(buf: &[u8], pos: usize) -> Option<u16> {
    buf.get(pos..pos + 2)
        .and_then(|b| b.try_into().ok())
        .map(u16::from_le_bytes)
}

/// Lee u16 big-endian desde un slice en `pos`.
fn be_u16(buf: &[u8], pos: usize) -> Option<u16> {
    buf.get(pos..pos + 2)
        .and_then(|b| b.try_into().ok())
        .map(u16::from_be_bytes)
}

fn le_u32(buf: &[u8], pos: usize) -> Option<u32> {
    buf.get(pos..pos + 4)
        .and_then(|b| b.try_into().ok())
        .map(u32::from_le_bytes)
}

fn be_u32(buf: &[u8], pos: usize) -> Option<u32> {
    buf.get(pos..pos + 4)
        .and_then(|b| b.try_into().ok())
        .map(u32::from_be_bytes)
}

/// Detecta la marca de la cámara a partir de los primeros bytes de los MakerNotes.
enum Brand {
    Nikon,
    Sony,
    Canon,
    Unknown,
}

fn detect_brand(makernote: &[u8]) -> Brand {
    if makernote.starts_with(b"Nikon\x00") {
        Brand::Nikon
    } else if makernote.starts_with(b"SONY DSC") || makernote.starts_with(b"SONY CAM") {
        Brand::Sony
    } else if makernote.starts_with(b"Canon") {
        Brand::Canon
    } else {
        // Intentar heurística por estructura IFD
        Brand::Unknown
    }
}

// ---------------------------------------------------------------------------
// Nikon
// ---------------------------------------------------------------------------

fn parse_nikon(makernote: &[u8]) -> Option<FocusPoint> {
    // Los MakerNotes de Nikon tienen un sub-TIFF embebido a partir del byte 10.
    // Formato: "Nikon\0" (6) + version (4) + TIFF header (8) + IFDs
    let tiff_start: usize = 10;
    if makernote.len() < tiff_start + 8 {
        return None;
    }
    let tiff = &makernote[tiff_start..];
    let le = &tiff[0..2] == b"II";
    let ifd0 = if le {
        u32::from_le_bytes(tiff[4..8].try_into().ok()?) as usize
    } else {
        u32::from_be_bytes(tiff[4..8].try_into().ok()?) as usize
    };

    let entry_count = if le {
        le_u16(tiff, ifd0)? as usize
    } else {
        be_u16(tiff, ifd0)? as usize
    };

    for i in 0..entry_count {
        let ep = ifd0 + 2 + i * 12;
        if ep + 12 > tiff.len() {
            break;
        }
        let tag = if le { le_u16(tiff, ep)? } else { be_u16(tiff, ep)? };
        // Tag 0x00B7 = AFInfo3 (D5/Z series), 0x0022 = AFInfo2 (D3/D4/D800…)
        if tag == 0x00B7 || tag == 0x0022 {
            let offset = if le {
                u32::from_le_bytes(tiff[ep + 8..ep + 12].try_into().ok()?) as usize
            } else {
                u32::from_be_bytes(tiff[ep + 8..ep + 12].try_into().ok()?) as usize
            };
            if offset + 4 < tiff.len() {
                let af_data = &tiff[offset..];
                // AFInfo2: byte 0 = AF areas used, bytes 2-3 = active point X, 4-5 = active point Y
                let af_points_total = af_data.get(0).copied().unwrap_or(1).max(1) as f32;
                let active_x = le_u16(af_data, 2).unwrap_or(0) as f32;
                let active_y = le_u16(af_data, 4).unwrap_or(0) as f32;
                let focused = af_data.get(6).copied().unwrap_or(0) == 1;
                return Some(FocusPoint {
                    x: (active_x / af_points_total).clamp(0.0, 1.0),
                    y: (active_y / af_points_total).clamp(0.0, 1.0),
                    is_focused: focused,
                });
            }
        }
    }
    None
}

// ---------------------------------------------------------------------------
// Sony
// ---------------------------------------------------------------------------

fn parse_sony(makernote: &[u8]) -> Option<FocusPoint> {
    // Sony MakerNotes: IFD en LE a partir del byte 12 (después del header "SONY DSC ").
    let ifd_start: usize = 12;
    if makernote.len() < ifd_start + 2 {
        return None;
    }
    let entry_count = le_u16(makernote, ifd_start)? as usize;
    for i in 0..entry_count {
        let ep = ifd_start + 2 + i * 12;
        if ep + 12 > makernote.len() {
            break;
        }
        let tag = le_u16(makernote, ep)?;
        // 0x0094 = AFPointSelected, 0x2010 = AFInfo (Alpha bodies)
        if tag == 0x0094 || tag == 0x2010 {
            let offset = u32::from_le_bytes(
                makernote.get(ep + 8..ep + 12)?.try_into().ok()?,
            ) as usize;
            let af_data = makernote.get(offset..offset + 8)?;
            let grid_w = le_u16(af_data, 0).unwrap_or(25).max(1) as f32;
            let grid_h = le_u16(af_data, 2).unwrap_or(17).max(1) as f32;
            let point_x = le_u16(af_data, 4).unwrap_or(0) as f32;
            let point_y = le_u16(af_data, 6).unwrap_or(0) as f32;
            return Some(FocusPoint {
                x: (point_x / grid_w).clamp(0.0, 1.0),
                y: (point_y / grid_h).clamp(0.0, 1.0),
                is_focused: true, // Sony no expone confirmed-focus en este tag
            });
        }
    }
    None
}

// ---------------------------------------------------------------------------
// Canon
// ---------------------------------------------------------------------------

fn parse_canon(makernote: &[u8]) -> Option<FocusPoint> {
    // Canon MakerNotes: IFD en LE inmediatamente (sin header "Canon").
    // Tag 0x0026 = AFInfo2
    if makernote.len() < 2 {
        return None;
    }
    let entry_count = le_u16(makernote, 0)? as usize;
    for i in 0..entry_count {
        let ep = 2 + i * 12;
        if ep + 12 > makernote.len() {
            break;
        }
        let tag = le_u16(makernote, ep)?;
        if tag == 0x0026 {
            let offset =
                u32::from_le_bytes(makernote.get(ep + 8..ep + 12)?.try_into().ok()?) as usize;
            let af_data = makernote.get(offset..offset + 16)?;
            // AFInfo2: word[0]=count, word[1]=AF mode, word[3]=valid point X, word[4]=valid point Y
            let count = le_u16(af_data, 0).unwrap_or(1).max(1) as f32;
            let pt_x = le_u16(af_data, 6).unwrap_or(0) as f32;
            let pt_y = le_u16(af_data, 8).unwrap_or(0) as f32;
            let focused = le_u16(af_data, 14).unwrap_or(0) > 0;
            return Some(FocusPoint {
                x: (pt_x / count).clamp(0.0, 1.0),
                y: (pt_y / count).clamp(0.0, 1.0),
                is_focused: focused,
            });
        }
    }
    None
}

// ---------------------------------------------------------------------------
// API pública
// ---------------------------------------------------------------------------

/// Extrae el punto de enfoque activo de un bloque de bytes MakerNote EXIF.
/// Retorna `None` si el fabricante no está soportado o si no hay datos de AF.
pub fn extract_focus_point_from_bytes(makernote: &[u8]) -> Option<FocusPoint> {
    match detect_brand(makernote) {
        Brand::Nikon => parse_nikon(makernote),
        Brand::Sony => parse_sony(makernote),
        Brand::Canon => parse_canon(makernote),
        Brand::Unknown => None,
    }
}

/// Extrae el punto de enfoque leyendo directamente el archivo RAW/JPEG.
/// Para uso desde Python via PyO3: retorna `(x, y, is_focused)` o `None`.
pub fn extract_focus_point(raw_path: &str) -> Option<FocusPoint> {
    // Leer los primeros 64 KB (suficiente para el bloque APP1/EXIF)
    use std::fs::File;
    use std::io::Read;
    let mut file = File::open(raw_path).ok()?;
    let mut buf = vec![0u8; 65536];
    let n = file.read(&mut buf).ok()?;
    buf.truncate(n);

    // Buscar el segmento MakerNote dentro del bloque EXIF
    // (búsqueda heurística: 'Nikon\0', 'SONY', 'Canon' en los primeros 64 KB)
    for window in [b"Nikon\x00".as_slice(), b"SONY DSC".as_slice(), b"Canon".as_slice()] {
        if let Some(pos) = buf.windows(window.len()).position(|w| w == window) {
            return extract_focus_point_from_bytes(&buf[pos..]);
        }
    }
    None
}

// ---------------------------------------------------------------------------
// Burst ID Extraction (MakerNotes)
// ---------------------------------------------------------------------------

fn extract_burst_id_from_bytes(makernote: &[u8]) -> Option<u32> {
    match detect_brand(makernote) {
        Brand::Sony => {
            let ifd_start: usize = 12;
            if makernote.len() < ifd_start + 2 { return None; }
            let entry_count = le_u16(makernote, ifd_start)? as usize;
            for i in 0..entry_count {
                let ep = ifd_start + 2 + i * 12;
                if ep + 12 > makernote.len() { break; }
                let tag = le_u16(makernote, ep)?;
                if tag == 0x200B || tag == 0x0017 { // SequenceImageNumber o SequenceNumber
                    return le_u32(makernote, ep + 8).or_else(|| le_u16(makernote, ep + 8).map(|v| v as u32));
                }
            }
            None
        },
        Brand::Nikon => {
            let tiff_start: usize = 10;
            if makernote.len() < tiff_start + 8 { return None; }
            let tiff = &makernote[tiff_start..];
            let le = &tiff[0..2] == b"II";
            let ifd0 = if le { u32::from_le_bytes(tiff[4..8].try_into().ok()?) as usize } else { u32::from_be_bytes(tiff[4..8].try_into().ok()?) as usize };
            let entry_count = if le { le_u16(tiff, ifd0)? as usize } else { be_u16(tiff, ifd0)? as usize };
            for i in 0..entry_count {
                let ep = ifd0 + 2 + i * 12;
                if ep + 12 > tiff.len() { break; }
                let tag = if le { le_u16(tiff, ep)? } else { be_u16(tiff, ep)? };
                if tag == 0x001D || tag == 0x0019 { // SequenceNumber
                    let val = if le { le_u32(tiff, ep + 8) } else { be_u32(tiff, ep + 8) };
                    return val.or_else(|| if le { le_u16(tiff, ep + 8).map(|v| v as u32) } else { be_u16(tiff, ep + 8).map(|v| v as u32) });
                }
            }
            None
        },
        Brand::Canon => {
            if makernote.len() < 2 { return None; }
            let entry_count = le_u16(makernote, 0)? as usize;
            for i in 0..entry_count {
                let ep = 2 + i * 12;
                if ep + 12 > makernote.len() { break; }
                let tag = le_u16(makernote, ep)?;
                if tag == 0x0004 { // RecordMode / DriveMode
                    return le_u16(makernote, ep + 8).map(|v| v as u32);
                }
            }
            None
        },
        Brand::Unknown => None,
    }
}

/// Extrae el Burst ID / Sequence Number de los MakerNotes
pub fn extract_burst_id(raw_path: &str) -> Option<u32> {
    use std::fs::File;
    use std::io::Read;
    let mut file = File::open(raw_path).ok()?;
    let mut buf = vec![0u8; 65536];
    let n = file.read(&mut buf).ok()?;
    buf.truncate(n);

    for window in [b"Nikon\x00".as_slice(), b"SONY DSC".as_slice(), b"Canon".as_slice()] {
        if let Some(pos) = buf.windows(window.len()).position(|w| w == window) {
            return extract_burst_id_from_bytes(&buf[pos..]);
        }
    }
    None
}
