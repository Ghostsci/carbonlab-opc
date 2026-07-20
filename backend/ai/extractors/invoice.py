"""Chinese invoice field extractor."""

import re


class InvoiceExtractor:
    PATTERNS = {
        "invoice_code": r"发票代码[：:]\s*(\d{10,12})",
        "invoice_number": r"发票号码[：:]\s*(\d{8})",
        "date": r"开票日期[：:]\s*(\d{4}年\d{1,2}月\d{1,2}日)",
        "seller_name": r"名\s*称[：:]\s*(\S+?公司)",
        "seller_tax_id": r"纳税人识别号[：:]\s*(\w{15,20})",
        "buyer_name": r"(?:购买方|购货方).*?名\s*称[：:]\s*(\S+?公司)",
        "buyer_tax_id": r"(?:购买方|购货方).*?纳税人识别号[：:]\s*(\w{15,20})",
        "total_amount": r"价税合计[（(]大写[)）]?\s*\S*?\s*[¥￥]\s*([\d,]+\.?\d*)",
        "tax_amount": r"税额[：:]\s*[¥￥]?\s*([\d,]+\.?\d*)",
        "amount_excluding_tax": r"(?:金额|不含税金额)[：:]\s*[¥￥]?\s*([\d,]+\.?\d*)",
    }

    def extract(self, text: str) -> dict[str, str]:
        fields = {}
        for key, pattern in self.PATTERNS.items():
            match = re.search(pattern, text)
            fields[key] = match.group(1).replace(",", "") if match else ""
        return fields
