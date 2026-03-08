"""
Universal LLM client supporting any OpenAI-compatible API.
Works with: OpenAI, Claude, Gemini, DeepSeek, Qwen, local models, etc.
"""

from __future__ import annotations

import base64
import httpx
import aiohttp
from openai import OpenAI, AsyncOpenAI
from typing import Optional, Union, List
from pathlib import Path


class LLMClient:
    """
    Universal LLM client using OpenAI-compatible API format.
    
    Examples:
        # OpenAI
        client = LLMClient(
            api_key="sk-xxx",
            base_url="https://api.openai.com/v1",
            model="gpt-4o"
        )
        
        # Claude (via OpenAI-compatible endpoint)
        client = LLMClient(
            api_key="sk-ant-xxx",
            base_url="https://api.anthropic.com/v1",
            model="claude-sonnet-4-20250514"
        )
        
        # DeepSeek
        client = LLMClient(
            api_key="sk-xxx",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat"
        )
        
        # Gemini (via OpenAI-compatible endpoint)
        client = LLMClient(
            api_key="xxx",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            model="gemini-2.0-flash"
        )
        
        # Local (Ollama, vLLM, etc.)
        client = LLMClient(
            base_url="http://localhost:11434/v1",
            model="llama3"
        )
    """
    
    # 已知支持直接传 PDF 的模型前缀
    PDF_NATIVE_MODELS = ["claude", "gemini"]
    
    def __init__(
        self,
        api_key: str = None,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout: int = 120,
        debug_save_pdfs: bool = False,  # 是否保存PDF到本地用于调试
        debug_pdf_dir: str = "debug_pdfs",  # PDF保存目录
        pdf_max_pages: int = 10,  # PDF最大页数（0表示不限制）
    ):
        self.model = model
        self.base_url = base_url
        self.debug_save_pdfs = debug_save_pdfs
        self.debug_pdf_dir = debug_pdf_dir
        self.pdf_max_pages = pdf_max_pages
        
        # 检测是否是 Anthropic API（需要特殊处理）
        self.is_anthropic = "anthropic.com" in base_url
        
        if self.is_anthropic:
            # Anthropic 有自己的 SDK，但也可以用 OpenAI 兼容模式
            # 这里我们用原生 Anthropic SDK 以支持 PDF
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
            self.async_client = anthropic.AsyncAnthropic(api_key=api_key)
        else:
            self.client = OpenAI(
                api_key=api_key or "not-needed",  # 本地模型可能不需要
                base_url=base_url,
                timeout=httpx.Timeout(timeout),
            )
            self.async_client = AsyncOpenAI(
                api_key=api_key or "not-needed",
                base_url=base_url,
                timeout=httpx.Timeout(timeout),
            )
    
    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4000,
        temperature: float = 0.7,
    ) -> str:
        """Synchronous chat completion."""
        if self.is_anthropic:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=messages,
            )
            return response.content[0].text
        else:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content
    
    async def achat(
        self,
        messages: list[dict],
        max_tokens: int = 4000,
        temperature: float = 0.7,
    ) -> str:
        """Async chat completion."""
        if self.is_anthropic:
            response = await self.async_client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=messages,
            )
            return response.content[0].text
        else:
            response = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content
    
    async def achat_with_pdf(
        self,
        prompt: str,
        pdf_path: Optional[str] = None,
        pdf_url: Optional[str] = None,
        pdf_base64: Optional[str] = None,
        max_tokens: int = 4000,
    ) -> str:
        """
        Chat with a PDF document (async version).
        
        Args:
            prompt: The user prompt
            pdf_path: Local path to PDF file
            pdf_url: URL to PDF (will be downloaded)
            pdf_base64: Base64-encoded PDF content
            max_tokens: Maximum response tokens
        """
        # Get PDF as base64
        if pdf_base64:
            pdf_data = pdf_base64
        elif pdf_path:
            pdf_data = self._file_to_base64(pdf_path)
        elif pdf_url:
            pdf_data = await self._url_to_base64_async(
                pdf_url, 
                save_debug=getattr(self, 'debug_save_pdfs', False),
                debug_dir=getattr(self, 'debug_pdf_dir', 'debug_pdfs'),
                max_pages=getattr(self, 'pdf_max_pages', 10)
            )
            if pdf_data is None:
                raise ValueError(f"Failed to download PDF from {pdf_url}")
        else:
            raise ValueError("Must provide pdf_path, pdf_url, or pdf_base64")
        
        if self.is_anthropic:
            # Anthropic native PDF support
            messages = [{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_data,
                        }
                    },
                    {"type": "text", "text": prompt}
                ]
            }]
            response = await self.async_client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=messages,
            )
            return response.content[0].text
        
        elif self.supports_pdf_native():
            # Gemini-style (via OpenAI compat, may vary)
            messages = [{
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {
                            "filename": "paper.pdf",
                            "file_data": f"data:application/pdf;base64,{pdf_data}"
                        }
                    },
                    {"type": "text", "text": prompt}
                ]
            }]
            return await self.achat(messages, max_tokens=max_tokens)
        
        else:
            # Fallback: extract text and send as text
            text = self._extract_pdf_text_from_base64(pdf_data)
            messages = [{
                "role": "user", 
                "content": f"{prompt}\n\n---\nPaper content:\n{text[:30000]}"
            }]
            return await self.achat(messages, max_tokens=max_tokens)
    
    async def achat_with_multiple_pdfs(
        self,
        prompt: str,
        pdf_urls: List[str],
        max_tokens: int = 4000,
    ) -> tuple[str, List[int]]:
        """
        Chat with multiple PDF documents (async).
        Only works with models that support multiple documents in one message.
        
        Args:
            prompt: The user prompt
            pdf_urls: List of PDF URLs
            max_tokens: Maximum response tokens
        
        Returns:
            Tuple of (response_text, list_of_failed_indices)
        """
        if not pdf_urls:
            raise ValueError("Must provide at least one PDF URL")
        
        # Download all PDFs
        pdf_data_list = []
        failed_indices = []
        
        for i, url in enumerate(pdf_urls):
            pdf_data = await self._url_to_base64_async(
                url, 
                save_debug=getattr(self, 'debug_save_pdfs', False),
                max_pages=getattr(self, 'pdf_max_pages', 10)
            )
            if pdf_data is None:
                failed_indices.append(i)
                pdf_data_list.append(None)
            else:
                pdf_data_list.append(pdf_data)
        
        # 检查是否有成功的PDF
        successful_pdfs = [d for d in pdf_data_list if d is not None]
        if not successful_pdfs:
            raise ValueError("All PDF downloads failed")
        
        if self.is_anthropic:
            # Anthropic supports multiple documents
            content = []
            for pdf_data in pdf_data_list:
                if pdf_data is not None:
                    content.append({
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_data,
                        }
                    })
            
            # 如果有失败的PDF，在prompt中说明
            if failed_indices:
                failed_note = f"\n\n注意：有 {len(failed_indices)} 篇论文的PDF下载失败，将仅基于摘要进行分析。"
                prompt = prompt + failed_note
            
            content.append({"type": "text", "text": prompt})
            
            messages = [{"role": "user", "content": content}]
            response = await self.async_client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=messages,
            )
            return response.content[0].text, failed_indices
        
        else:
            # For other models, fallback to processing one by one or text extraction
            # This is a simplified fallback - you might want to implement batch processing
            raise NotImplementedError("Multiple PDFs not yet supported for this model. Use achat_with_pdf for single PDFs.")
    
    def supports_pdf_native(self) -> bool:
        """Check if this model supports native PDF input."""
        model_lower = self.model.lower()
        return any(prefix in model_lower for prefix in self.PDF_NATIVE_MODELS)
    
    def chat_with_pdf(
        self,
        prompt: str,
        pdf_path: Optional[str] = None,
        pdf_url: Optional[str] = None,
        pdf_base64: Optional[str] = None,
        max_tokens: int = 4000,
    ) -> str:
        """
        Chat with a PDF document.
        
        Args:
            prompt: The user prompt
            pdf_path: Local path to PDF file
            pdf_url: URL to PDF (will be downloaded)
            pdf_base64: Base64-encoded PDF content
            max_tokens: Maximum response tokens
        """
        # Get PDF as base64
        if pdf_base64:
            pdf_data = pdf_base64
        elif pdf_path:
            pdf_data = self._file_to_base64(pdf_path)
        elif pdf_url:
            pdf_data = self._url_to_base64(pdf_url)
        else:
            raise ValueError("Must provide pdf_path, pdf_url, or pdf_base64")
        
        if self.is_anthropic:
            # Anthropic native PDF support
            messages = [{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_data,
                        }
                    },
                    {"type": "text", "text": prompt}
                ]
            }]
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=messages,
            )
            return response.content[0].text
        
        elif self.supports_pdf_native():
            # Gemini-style (via OpenAI compat, may vary)
            messages = [{
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {
                            "filename": "paper.pdf",
                            "file_data": f"data:application/pdf;base64,{pdf_data}"
                        }
                    },
                    {"type": "text", "text": prompt}
                ]
            }]
            return self.chat(messages, max_tokens=max_tokens)
        
        else:
            # Fallback: extract text and send as text
            text = self._extract_pdf_text_from_base64(pdf_data)
            messages = [{
                "role": "user", 
                "content": f"{prompt}\n\n---\nPaper content:\n{text[:30000]}"
            }]
            return self.chat(messages, max_tokens=max_tokens)
    
    def _file_to_base64(self, path: str) -> str:
        """Read file and convert to base64."""
        with open(path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode("utf-8")
    
    def _url_to_base64(self, url: str) -> str:
        """Download URL and convert to base64."""
        import httpx
        response = httpx.get(url, follow_redirects=True, timeout=60)
        response.raise_for_status()
        return base64.standard_b64encode(response.content).decode("utf-8")
    
    async def _url_to_base64_async(
        self, 
        url: str, 
        save_debug: bool = False, 
        debug_dir: str = "debug_pdfs",
        max_pages: int = 10
    ) -> Optional[str]:
        """Download URL and convert to base64 (async). Returns None if download fails.
        
        Args:
            url: PDF URL to download
            save_debug: If True, save PDF to local file for debugging
            debug_dir: Directory to save debug PDFs
            max_pages: Maximum number of pages to extract (default: 10, set to 0 for all pages)
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status != 200:
                        print(f"      ⚠️ PDF download failed: HTTP {response.status}")
                        return None
                    content = await response.read()
                    
                    # 简单检查是否是PDF
                    if not content.startswith(b'%PDF'):
                        print(f"      ⚠️ Downloaded content is not a valid PDF (doesn't start with %PDF)")
                        return None
                    
                    # 如果指定了最大页数，提取前N页
                    if max_pages > 0:
                        try:
                            import fitz  # PyMuPDF
                            doc = fitz.open(stream=content, filetype="pdf")
                            total_pages = len(doc)
                            
                            if total_pages > max_pages:
                                # 创建新PDF，只包含前N页
                                new_doc = fitz.open()
                                new_doc.insert_pdf(doc, from_page=0, to_page=max_pages - 1)
                                # 将新PDF保存到内存
                                content = new_doc.tobytes()
                                new_doc.close()
                                print(f"      📄 Extracted first {max_pages} pages (total: {total_pages} pages)")
                            else:
                                print(f"      📄 PDF has {total_pages} pages (≤ {max_pages}, using all)")
                            
                            doc.close()
                        except ImportError:
                            print(f"      ⚠️ PyMuPDF not available, using full PDF")
                        except Exception as e:
                            print(f"      ⚠️ Failed to extract pages: {e}, using full PDF")
                    
                    # 调试：保存PDF到本地（如果启用）
                    if save_debug:
                        import os
                        from pathlib import Path
                        os.makedirs(debug_dir, exist_ok=True)
                        # 从URL提取文件名
                        filename = url.split('/')[-1].split('?')[0] or "paper.pdf"
                        if not filename.endswith('.pdf'):
                            filename += '.pdf'
                        filepath = Path(debug_dir) / filename
                        with open(filepath, 'wb') as f:
                            f.write(content)
                        print(f"      💾 Debug: PDF saved to {filepath} ({len(content)} bytes)")
                    
                    pdf_base64 = base64.standard_b64encode(content).decode("utf-8")
                    print(f"      ✓ PDF processed: {len(content)} bytes -> base64 length: {len(pdf_base64)}")
                    return pdf_base64
        except Exception as e:
            url_preview = str(url)[:50] if url is not None else "<none>"
            print(f"      ⚠️ PDF download failed for {url_preview}...: {e}")
            return None
    
    def _extract_pdf_text_from_base64(self, pdf_base64: str) -> str:
        """Extract text from base64-encoded PDF."""
        try:
            import fitz  # PyMuPDF
            pdf_bytes = base64.b64decode(pdf_base64)
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            return text
        except ImportError:
            return "[PDF text extraction unavailable - install pymupdf]"
        except Exception as e:
            return f"[PDF extraction error: {e}]"


# Convenience presets
def openai_client(api_key: str, model: str = "gpt-4o-mini") -> LLMClient:
    return LLMClient(api_key=api_key, base_url="https://api.openai.com/v1", model=model)

def claude_client(api_key: str, model: str = "claude-sonnet-4-20250514") -> LLMClient:
    return LLMClient(api_key=api_key, base_url="https://api.anthropic.com/v1", model=model)

def deepseek_client(api_key: str, model: str = "deepseek-chat") -> LLMClient:
    return LLMClient(api_key=api_key, base_url="https://api.deepseek.com/v1", model=model)

def gemini_client(api_key: str, model: str = "gemini-2.0-flash") -> LLMClient:
    return LLMClient(
        api_key=api_key, 
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model=model
    )

def qwen_client(api_key: str, model: str = "qwen-turbo") -> LLMClient:
    return LLMClient(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model=model
    )

def local_client(base_url: str = "http://localhost:11434/v1", model: str = "llama3") -> LLMClient:
    return LLMClient(base_url=base_url, model=model)
