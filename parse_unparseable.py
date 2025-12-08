#!/usr/bin/env python3
"""Parse unparseable products CSV and fill in missing brand, series, model fields."""

import csv
import re
import sys

def parse_product_name(raw_name, product_type):
    """Parse product name to extract brand, series, and model."""
    if not raw_name:
        return None, None, None
    
    raw_upper = raw_name.upper()
    brand = None
    series = None
    model = None
    
    # Brand patterns
    brand_patterns = [
        (r'^SEGOTEP\s+', 'SEGOTEP'),
        (r'^GAMEMAX\s+', 'GAMEMAX'),
        (r'^MONTECH\s+', 'MONTECH'),
        (r'^DIYPC\s+', 'DIYPC'),
        (r'^THERMALRIGHT\s+', 'THERMALRIGHT'),
        (r'^LUKYAMZN\s+', 'LUKYAMZN'),
        (r'^CRUCIAL\s+', 'CRUCIAL'),
        (r'^G\.SKILL\s+', 'G.SKILL'),
        (r'^SAMSUNG\s+', 'SAMSUNG'),
        (r'^SANDISK\s+', 'SANDISK'),
        (r'^WD\s+', 'WD'),
        (r'^TEAM\s+', 'TEAM'),
        (r'^SEAGATE\s+', 'SEAGATE'),
        (r'^LG\s+', 'LG'),
        (r'^ONN\.\s+', 'ONN'),
        (r'^ACER\s+', 'ACER'),
        (r'^DELL\s+', 'DELL'),
        (r'^CORSAIR\s+', 'CORSAIR'),
        (r'^HYPERX\s+', 'HYPERX'),
        (r'^ANKER\s+', 'ANKER'),
        (r'^BOSE\s+', 'BOSE'),
        (r'^TZUMI\s+', 'TZUMI'),
        (r'^JLAB\s+', 'JLAB'),
        (r'^BEATS\s+', 'BEATS'),
        (r'^SKULLCANDY\s+', 'SKULLCANDY'),
        (r'^GABBAGOODS\s+', 'GABBAGOODS'),
        (r'^JBL\s+', 'JBL'),
        (r'^ULTIMATE\s+EARS\s+', 'ULTIMATE EARS'),
        (r'^BEFREE\s+SOUND\s+', 'BEFREE SOUND'),
        (r'^ADAFRUIT\s+', 'ADAFRUIT'),
        (r'^MOVO\s+', 'MOVO'),
        (r'^GLUAAE\s+', 'GLUAAE'),
        (r'^RODE\s+', 'RODE'),
        (r'^AUDIO-TECHNICA\s+', 'AUDIO-TECHNICA'),
        (r'^BLUE\s+', 'BLUE'),
        (r'^FIFINE\s+', 'FIFINE'),
        (r'^INTEL\s+', 'INTEL'),
        (r'^AMD\s+', 'AMD'),
        (r'^VISIONTEK\s+', 'VISIONTEK'),
        (r'^NVIDIA\s+', 'NVIDIA'),
        (r'^GIGABYTE\s+', 'GIGABYTE'),
        (r'^ASUS\s+', 'ASUS'),
        (r'^ASROCK\s+', 'ASROCK'),
        (r'^SUPERMICRO\s+', 'SUPERMICRO'),
        (r'^BIOSTAR\s+', 'BIOSTAR'),
        (r'^HUANANZHI\s+', 'HUANANZHI'),
        (r'^COOLER\s+MASTER\s+', 'COOLER MASTER'),
        (r'^NZXT\s+', 'NZXT'),
        (r'^SEASONIC\s+', 'SEASONIC'),
        (r'^LIAN\s+LI\s+', 'LIAN LI'),
        (r'^SILVERSTONE\s+', 'SILVERSTONE'),
        (r'^THERMALTAKE\s+', 'THERMALTAKE'),
        (r'^MSI\s+', 'MSI'),
        (r'^BE\s+QUIET!\s+', 'BE QUIET'),
        (r'^BE\s+QUIET\s+', 'BE QUIET'),
        (r'^FSP\s+', 'FSP'),
        (r'^SAMA\s+', 'SAMA'),
        (r'^NOCTUA\s+', 'NOCTUA'),
        (r'^FRACTAL\s+DESIGN\s+', 'FRACTAL DESIGN'),
        (r'^PNY\s+', 'PNY'),
        (r'^KINGSTON\s+', 'KINGSTON'),
        (r'^HYTE\s+', 'HYTE'),
        (r'^VETROO\s+', 'VETROO'),
        (r'^PCCOOLER\s+', 'PCCOOLER'),
        (r'^ROSEWILL\s+', 'ROSEWILL'),
        (r'^ZALMAN\s+', 'ZALMAN'),
    ]
    
    for pattern, b in brand_patterns:
        if re.match(pattern, raw_upper):
            brand = b
            break
    
    if not brand:
        words = raw_name.split()
        if words and len(words[0]) > 2:
            brand = words[0].upper()
    
    # Product-specific parsing
    if product_type == 'psu':
        wattage_match = re.search(r'(\d+)\s*W', raw_upper)
        if wattage_match:
            series = wattage_match.group(1) + 'W'
        cert_match = re.search(r'(80\s*PLUS\s*(?:PLATINUM|GOLD|BRONZE|SILVER)?|PLATINUM|GOLD|BRONZE)', raw_upper)
        if cert_match:
            model = cert_match.group(1).replace(' ', '')
        model_match = re.search(r'(SF\d+|V\d+|MWE|PRIME|TOUGHPOWER|PURE\s+POWER)', raw_upper)
        if model_match:
            model = model_match.group(1).replace(' ', '')
            
    elif product_type == 'case':
        form_match = re.search(r'(ATX|MICRO\s*ATX|MINI\s*ATX|ITX|MINI-ITX|E-ATX)', raw_upper)
        if form_match:
            series = form_match.group(1).replace(' ', '-')
        model_match = re.search(r'\b([A-Z]\d+[A-Z]?|[A-Z]{2,}\d*)\b', raw_name)
        if model_match:
            potential_model = model_match.group(1)
            if potential_model not in ['ATX', 'ITX', 'SSD', 'RGB', 'ARGB', 'USB', 'PCI', 'PCIe']:
                model = potential_model
                
    elif product_type == 'cooling':
        if 'PEERLESS ASSASSIN' in raw_upper:
            series = 'Peerless Assassin'
            size_match = re.search(r'(\d+)\s*MM?', raw_upper)
            if size_match:
                model = size_match.group(1) + 'mm'
        elif 'ASSASSIN' in raw_upper:
            series = 'Assassin'
            size_match = re.search(r'(\d+)\s*MM?', raw_upper)
            if size_match:
                model = size_match.group(1) + 'mm'
        elif 'SPIRIT' in raw_upper:
            series = 'Spirit'
            size_match = re.search(r'(\d+)\s*MM?', raw_upper)
            if size_match:
                model = size_match.group(1) + 'mm'
        elif 'KING' in raw_upper:
            series = 'King'
            size_match = re.search(r'(\d+)\s*MM?', raw_upper)
            if size_match:
                model = size_match.group(1) + 'mm'
        elif 'ARGB' in raw_upper and not series:
            series = 'CPU Cooler'
            model = 'ARGB'
        else:
            model_match = re.search(r'\b([A-Z]\d+[A-Z]?|[A-Z]{2,}\d*)\b', raw_name)
            if model_match:
                model = model_match.group(1)
        if not series:
            size_match = re.search(r'(\d+)\s*MM', raw_upper)
            if size_match:
                series = size_match.group(1) + 'mm'
                
    elif product_type == 'ram':
        ddr_match = re.search(r'(DDR[345])', raw_upper)
        if ddr_match:
            series = ddr_match.group(1)
        speed_match = re.search(r'(\d+)\s*MHZ', raw_upper)
        if speed_match:
            model = speed_match.group(1) + 'MHz'
        if not model:
            cap_match = re.search(r'(\d+)\s*GB', raw_upper)
            if cap_match:
                model = cap_match.group(1) + 'GB'
        if not series:
            if 'FLARE X5' in raw_upper or ('FLARE' in raw_upper and 'X5' in raw_upper):
                series = 'Flare X5'
            elif 'RIPJAWS' in raw_upper:
                series = 'Ripjaws'
            elif 'FLARE' in raw_upper:
                series = 'Flare'
            elif 'PRO' in raw_upper:
                series = 'Pro'
            elif 'X5' in raw_upper:
                series = 'Flare X5'
                
    elif product_type == 'internal_storage':
        # Extract model number first (like 990, 870, etc.)
        model_match = re.search(r'\b(\d{3,})\b', raw_name)
        if model_match:
            model = model_match.group(1)
        # Series is the product line
        if 'PRO' in raw_upper:
            series = 'PRO'
        elif 'EVO' in raw_upper:
            series = 'EVO'
        elif 'PLUS' in raw_upper:
            series = 'Plus'
        elif 'GREEN' in raw_upper:
            series = 'Green'
        if 'NVME' in raw_upper or 'M.2' in raw_upper:
            if not series:
                series = 'NVMe'
        elif 'SATA' in raw_upper:
            if not series:
                series = 'SATA'
        # For "T-Force G50", extract G50 as model
        if 'T-FORCE' in raw_upper or 'T-FORCE' in raw_name:
            g50_match = re.search(r'G(\d+)', raw_upper)
            if g50_match:
                model = 'G' + g50_match.group(1)
        # For "P310", extract as model
        p310_match = re.search(r'\bP(\d+)\b', raw_upper)
        if p310_match and not model:
            model = 'P' + p310_match.group(1)
                
    elif product_type == 'external_storage':
        if 'ONE TOUCH' in raw_upper:
            series = 'One Touch'
            # Model number like STKG500400
            stkg_match = re.search(r'STKG(\d+)', raw_upper)
            if stkg_match:
                model = 'STKG' + stkg_match.group(1)
            else:
                model = 'One Touch'  # Generic model if no specific number
        elif 'EXTREME' in raw_upper:
            series = 'Extreme'
        elif 'PORTABLE' in raw_upper:
            series = 'Portable'
            # For T7, T9 - these are models
            t_match = re.search(r'\bT(\d+)\b', raw_upper)
            if t_match:
                model = 'T' + t_match.group(1)
        elif 'MY PASSPORT' in raw_upper:
            series = 'My Passport'
            model = 'My Passport'
        elif 'X10' in raw_upper:
            series = 'X10'
            model = 'X10'
        elif 'CREATOR' in raw_upper:
            series = 'Creator'
            model = 'Creator'
        else:
            model_match = re.search(r'\b([A-Z]\d+)\b', raw_name)
            if model_match:
                model = model_match.group(1)
            
    elif product_type == 'monitor':
        size_match = re.search(r'(\d+)\"', raw_name)
        if size_match:
            series = size_match.group(1) + '"'
        if 'VIEWFINITY' in raw_upper:
            series = 'ViewFinity'
            s7_match = re.search(r'\bS(\d+)\b', raw_upper)
            if s7_match:
                model = 'S' + s7_match.group(1)
        elif 'ULTRAGEAR' in raw_upper:
            series = 'UltraGear'
            if not model:
                model = 'UltraGear'
        elif 'ULTRAWIDE' in raw_upper:
            series = 'UltraWide'
            if not model:
                model = 'UltraWide'
        elif 'NITRO' in raw_upper:
            series = 'Nitro'
            if not model:
                model = 'Nitro'
        # For "S2425h" extract as model
        s_match = re.search(r'\bS(\d+[A-Z]?)\b', raw_upper)
        if s_match:
            model = 'S' + s_match.group(1)
        # For generic monitors, use size as series if not set
        if not series and size_match:
            series = size_match.group(1) + '"'
        # For generic models, try to extract model code
        if not model:
            model_match = re.search(r'\b([A-Z]\d+[A-Z]?)\b', raw_name)
            if model_match:
                potential = model_match.group(1)
                if potential not in ['IPS', 'FHD', 'QHD', 'UHD', 'HDR', 'LED']:
                    model = potential
        # If still no model and has FHD/QHD/UHD, use that
        if not model:
            if 'FHD' in raw_upper:
                model = 'FHD'
            elif 'QHD' in raw_upper:
                model = 'QHD'
            elif 'UHD' in raw_upper or '4K' in raw_upper:
                model = 'UHD'
            
    elif product_type in ['mouse', 'headphones', 'speakers', 'microphone']:
        if 'QUIETCOMFORT' in raw_upper:
            series = 'QuietComfort'
            if 'ULTRA' in raw_upper:
                ultra_match = re.search(r'ULTRA\s*(\d+)', raw_upper)
                if ultra_match:
                    model = 'Ultra ' + ultra_match.group(1)
                else:
                    model = 'Ultra'
        elif 'SOUNDCORE' in raw_upper:
            series = 'Soundcore'
            q20i_match = re.search(r'Q(\d+I)', raw_upper)
            if q20i_match:
                model = 'Q' + q20i_match.group(1)
            else:
                # Check for number after Soundcore
                num_match = re.search(r'SOUNDCORE\s*(\d+)', raw_upper)
                if num_match:
                    model = num_match.group(1)
        elif 'SOLO' in raw_upper:
            series = 'Solo'
            solo_match = re.search(r'SOLO\s*(\d+)', raw_upper)
            if solo_match:
                model = 'Solo ' + solo_match.group(1)
            else:
                model = 'Solo'
        elif 'CRUSHER' in raw_upper:
            series = 'Crusher'
            if 'EVO' in raw_upper:
                model = 'Evo'
        elif 'PULSEFIRE' in raw_upper:
            series = 'Pulsefire'
            if 'SAGA' in raw_upper:
                model = 'Saga Pro'
            else:
                model = 'Pulsefire'
        elif 'M75' in raw_upper:
            model = 'M75'
        elif 'GO' in raw_upper and 'JBL' in raw_upper:
            go_match = re.search(r'GO\s*(\d+)', raw_upper)
            if go_match:
                model = 'Go ' + go_match.group(1)
            else:
                model = 'Go'
        elif 'FLIP' in raw_upper and 'JBL' in raw_upper:
            flip_match = re.search(r'FLIP\s*(\d+)', raw_upper)
            if flip_match:
                model = 'Flip ' + flip_match.group(1)
            else:
                model = 'Flip'
        elif 'STUDIO' in raw_upper:
            studio_match = re.search(r'STUDIO\s*(\d+)', raw_upper)
            if studio_match:
                model = 'Studio ' + studio_match.group(1)
            else:
                model = 'Studio'
        elif 'SOUNDPLAY' in raw_upper:
            series = 'Soundplay'
            model = 'Soundplay'
        elif 'MEGABASS' in raw_upper:
            series = 'Megabass'
            v_match = re.search(r'V(\d+)', raw_upper)
            if v_match:
                model = 'V' + v_match.group(1)
        elif 'BRITEBEATS' in raw_upper:
            series = 'BriteBeats'
            model = 'BriteBeats'
        # Generic model extraction
        if not model:
            # Look for model codes like M75, Q20i, V3, etc.
            model_match = re.search(r'\b([A-Z]\d+[A-Z]?|[A-Z]{2,}\d*)\b', raw_name)
            if model_match:
                potential = model_match.group(1)
                # Skip common words
                if potential not in ['USB', 'RGB', 'ARGB', 'PWM', 'WIRELESS', 'BLUETOOTH']:
                    model = potential
            
    elif product_type == 'cpu':
        if 'RYZEN' in raw_upper:
            series = 'Ryzen'
            ryzen_match = re.search(r'RYZEN\s*(\d+)\s*(\d{4}[X]?)', raw_upper)
            if ryzen_match:
                model = 'Ryzen ' + ryzen_match.group(1) + ' ' + ryzen_match.group(2)
            else:
                ryzen_match = re.search(r'RYZEN\s*(\d+)', raw_upper)
                if ryzen_match:
                    model = 'Ryzen ' + ryzen_match.group(1)
        elif 'INTEL' in raw_upper or 'CORE' in raw_upper:
            series = 'Core'
            core_match = re.search(r'(I[3579]|CORE\s*ULTRA\s*(\d+))', raw_upper)
            if core_match:
                model = core_match.group(1)
        elif 'XEON' in raw_upper:
            series = 'Xeon'
            xeon_match = re.search(r'XEON\s*([A-Z]\d+-\d+)', raw_upper)
            if xeon_match:
                model = xeon_match.group(1)
        elif 'THREADRIPPER' in raw_upper:
            series = 'Threadripper'
            
    elif product_type == 'gpu':
        if 'RTX' in raw_upper:
            series = 'RTX'
            rtx_match = re.search(r'RTX\s*(\d{4})', raw_upper)
            if rtx_match:
                model = 'RTX ' + rtx_match.group(1)
        elif 'GTX' in raw_upper:
            series = 'GTX'
            gtx_match = re.search(r'GTX\s*(\d{4})', raw_upper)
            if gtx_match:
                model = 'GTX ' + gtx_match.group(1)
        elif 'RADEON' in raw_upper or 'HD' in raw_upper:
            series = 'Radeon'
            hd_match = re.search(r'HD\s*(\d{4})', raw_upper)
            if hd_match:
                model = 'HD' + hd_match.group(1)
        elif 'H100' in raw_upper:
            series = 'H100'
            model = 'H100'
        elif 'A100' in raw_upper:
            series = 'A100'
            model = 'A100'
            
    elif product_type == 'motherboard':
        chipset_match = re.search(r'\b([A-Z]\d{3}[A-Z]?)\b', raw_name)
        if chipset_match:
            series = chipset_match.group(1)
        model_match = re.search(r'\b([A-Z]\d+[A-Z]?)\b', raw_name)
        if model_match:
            model = model_match.group(1)
    
    return brand, series, model


def main():
    csv_path = 'data/unparseable_products.csv'
    
    # Read the CSV
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames
    
    # Process each row
    updated = 0
    for row in rows:
        if not row.get('brand') or not row.get('series') or not row.get('model'):
            raw_name = row.get('raw_name', '')
            product_type = row.get('product_type', '')
            
            brand, series, model = parse_product_name(raw_name, product_type)
            
            if brand and not row.get('brand'):
                row['brand'] = brand
                updated += 1
            if series and not row.get('series'):
                row['series'] = series
                updated += 1
            if model and not row.get('model'):
                row['model'] = model
                updated += 1
    
    # Write back
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    print(f'Updated {updated} fields across {len(rows)} rows')
    
    # Count remaining missing
    missing = sum(1 for row in rows if not row.get('brand') or not row.get('series') or not row.get('model'))
    print(f'Remaining missing: {missing} rows')


if __name__ == '__main__':
    main()

